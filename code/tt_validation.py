import requests

import geopandas as gpd
import numpy as np
import matplotlib.pyplot as plt
from shapely.ops import unary_union
import rasterio
from rasterio.transform import rowcol
from skimage.graph import MCP, MCP_Geometric
import time
from rasterio.transform import from_bounds
from geopy.distance import distance
import os
from shapely.geometry import Polygon, MultiPolygon, Point, mapping
from rasterio.mask import mask
from rasterio.warp import reproject, Resampling, calculate_default_transform
import random
import compute_tts

import time
import random
import requests
from typing import Tuple, Optional, Dict, Any

from pyproj import Transformer

import geopandas as gpd
import argparse
import os
import shutil
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import rasterio
import scipy
import pickle
from tqdm import tqdm

from shapely.geometry import Polygon, MultiPolygon, Point, mapping

# local files

import centroids 
import compute_tts
import accessibility_metrics
# codes for the countries are taken from openAfrica's dataset (https://open.africa/dataset/africa-shapefiles/resource/dcdadd25-0137-4c93-ae5a-82b39d424d60)

import requests
import time
import random
from typing import Any, Dict, Optional, Tuple
from pyproj import Transformer


def transformer_to_wgs84(from_epsg: int) -> Transformer:
    return Transformer.from_crs(f"EPSG:{from_epsg}", "EPSG:4326", always_xy=True)

def xy_to_lonlat(t: Transformer, x: float, y: float) -> Tuple[float, float]:
    lon, lat = t.transform(x, y)
    return lon, lat

def ors_drive_time_seconds(
    api_key: str,
    mode: str,
    origin_xy: Tuple[float, float],
    dest_xy: Tuple[float, float],
    *,
    epsg: int,
    snap_radius_m: int = 2000,
    timeout_s: int = 20,
    min_spacing_s: float = 1.6,
    max_retries_429: int = 8,
    base_backoff_s: float = 1.0,
) -> Dict[str, Any]:

    if mode == 'walk':
        ORS_URL = "https://api.openrouteservice.org/v2/directions/foot-walking"
    elif mode == 'moto':
        ORS_URL = "https://api.openrouteservice.org/v2/directions/driving-car"
    t = transformer_to_wgs84(epsg)
    o_lon, o_lat = xy_to_lonlat(t, origin_xy[0], origin_xy[1])
    d_lon, d_lat = xy_to_lonlat(t, dest_xy[0], dest_xy[1])

    headers = {"Authorization": api_key, "Content-Type": "application/json"}
    body = {"coordinates": [[o_lon, o_lat], [d_lon, d_lat]], "radiuses": [snap_radius_m, snap_radius_m]}

    # pacing
    last_t = getattr(ors_drive_time_seconds, "_last_t", None)
    now = time.time()
    if last_t is not None:
        dt = now - last_t
        if dt < min_spacing_s:
            time.sleep(min_spacing_s - dt)

    last_err: Optional[str] = None

    for attempt in range(max_retries_429 + 1):
        r = requests.post(ORS_URL, json=body, headers=headers, timeout=timeout_s)

        if r.status_code == 429:
            ra = r.headers.get("Retry-After")
            try:
                sleep_for = float(ra) if ra else base_backoff_s * (2 ** attempt)
            except ValueError:
                sleep_for = base_backoff_s * (2 ** attempt)
            sleep_for += random.uniform(0, 0.25)
            time.sleep(sleep_for)
            last_err = f"429 Too Many Requests (slept {sleep_for:.2f}s)"
            continue

        # Parse JSON safely
        try:
            data: Any = r.json()
        except Exception:
            data = r.text  # string fallback

        if r.status_code != 200:
            msg = None
            if isinstance(data, dict):
                msg = (data.get("error", {}) or {}).get("message") or data.get("message")
            if not msg:
                msg = (data if isinstance(data, str) else str(data))[:500]
            raise RuntimeError(
                f"ORS HTTP {r.status_code}: {msg} | "
                f"origin_wgs84=({o_lat:.7f},{o_lon:.7f}) dest_wgs84=({d_lat:.7f},{d_lon:.7f})"
            )

        # Success payloads
        if isinstance(data, dict) and "routes" in data and data["routes"]:
            summary = data["routes"][0]["summary"]
            ors_drive_time_seconds._last_t = time.time()
            return {
                "duration_s": float(summary["duration"]),
                "distance_m": float(summary["distance"]),
                "origin_wgs84": (o_lat, o_lon),
                "dest_wgs84": (d_lat, d_lon),
            }

        if isinstance(data, dict) and "features" in data and data["features"]:
            summary = data["features"][0]["properties"]["summary"]
            ors_drive_time_seconds._last_t = time.time()
            return {
                "duration_s": float(summary["duration"]),
                "distance_m": float(summary["distance"]),
                "origin_wgs84": (o_lat, o_lon),
                "dest_wgs84": (d_lat, d_lon),
            }

        # If we got here, we got 200 but unexpected content
        raise RuntimeError(
            f"ORS returned 200 but unexpected payload type={type(data)} keys={list(data.keys()) if isinstance(data, dict) else 'n/a'} | "
            f"payload_snip={(data[:500] if isinstance(data, str) else str(data)[:500])}"
        )

    raise RuntimeError(f"ORS failed after retries. Last error: {last_err}")


def load_market_data(country_code:str, overlap_rad = 200):
    '''  
    Loads and joins market data from OSM and WFP 

    VARIABLES:
    --------------------------------------------------
    country_code (string): iso3 code of the country to load (lowercase)
    overlap_rad (float): overlap radious in meters

    OUTPUT:

    facility_gdf: Joined GeoDataFrame of OSM and WFP markets
    '''

    # read OSM data
    market_OSM = gpd.read_file('../shared_data/africa_markets/markets/'+country_code+'_markets_shops.geojson')
    print('Number of markets fron OSM:', len(market_OSM))
    crs = market_OSM.crs
    utm_crs = market_OSM.estimate_utm_crs()

    market_OSM = market_OSM.to_crs(utm_crs)
    # get centroids if markets are polygons
    market_OSM['geometry'] = market_OSM['geometry'].centroid
    market_OSM = market_OSM.to_crs(crs)

    # Load WFP data

    # Reading WFP Markets and getting the geometry column out of the .csv file

    market_WFP = pd.read_csv('../shared_data/markets_MFI_africa.csv')
    market_price = pd.read_csv('../shared_data/markets_price_africa.csv')

    market_WFP = pd.concat([market_WFP, market_price]).drop_duplicates(subset = 'MarketId', keep = 'first')

    market_WFP['geometry'] = [Point(xy) for xy in zip(market_WFP.Longitude, market_WFP.Latitude)]
    
    market_WFP = gpd.GeoDataFrame(market_WFP, geometry = 'geometry')
    
    market_WFP.drop(['Latitude', 'Longitude'], inplace = True, axis = 1)
    market_WFP = market_WFP.set_crs(crs)
    market_WFP = market_WFP.to_crs(utm_crs)

    print(len(market_WFP))

    # load the country borders
    country_borders = gpd.read_file('../shared_data/africa_markets/borders/'+country_code+'.geojson')
    country_borders = country_borders.to_crs(utm_crs)

    # Get the WFP markets from the country considered

    market_WFP_country= market_WFP.sjoin(country_borders)
    market_WFP_country.reset_index(inplace = True)
    
    print(f'Number of markets fron WFP in {country_code}:', len(market_WFP_country))

    # Now we merge the WFP and OSM datasets and set an overlap radious of 200m
    # go to UTM crs in both gdfs

    market_OSM = market_OSM.to_crs(utm_crs)
    OSM_points_x = np.array([point.x for point in market_OSM['geometry']])
    OSM_points_y = np.array([point.y for point in market_OSM['geometry']])
    same_points = []
    
    for i in range(len(market_WFP_country)):
        new_market = market_WFP_country['geometry'].iloc[i]
        dists_x = OSM_points_x - new_market.x
        dists_y = OSM_points_y - new_market.y

        dists = np.sqrt(dists_x**2 + dists_y**2)

        # if the dist. between markets is less than ri they are the same
        if np.min(dists) < overlap_rad:
            same_points.append(i)
            
    # drop the repeated points
    market_WFP_dropped = market_WFP_country.drop(index = same_points, axis = 0)
    
    # set a market ID
    # MFI_WFP_dropped['ID'] = list(range(max_ID+1, max_ID+len(MFI_WFP_dropped)+1))
    
    # concatenate the WFP and OSM dataframes
    market_gdf =  pd.concat([market_OSM,market_WFP_dropped])
    market_gdf = market_gdf.to_crs(crs)
    market_gdf['ID'] = np.arange(0, len(market_gdf))
    market_gdf = market_gdf[['ID', 'geometry']]
    
    facility_gdf = market_gdf.to_crs(utm_crs).sjoin(country_borders.to_crs(utm_crs), how = 'left')

    facility_gdf = facility_gdf.to_crs(crs)
    facility_gdf = facility_gdf.reset_index()
    facility_gdf = facility_gdf.drop_duplicates(subset = 'ID')
   
    facility_gdf = facility_gdf[['ID', 'geometry']]

    
    print('Total number of points', len(facility_gdf))
    print('Number of overlapping points at less than {0}m:'.format(overlap_rad), len(same_points))

    return(facility_gdf, country_borders.to_crs(crs))


# Adding colorbars
def fmt(x, pos):
    a, b = '{:.1e}'.format(x).split('e')
    b = int(b)
    if x!=0:
        return r'${} \times 10^{{{}}}$'.format(a, b)
    else:
        return '0'


def main(country_code, tmode):
    if tmode != 'moto' and tmode != "walk":
        msg = f"Chose a valid transport mode. Options walk for walking and moto for motorized. {tmode} is not valid"
        raise Exception(msg)

    if len(country_code) != 3:
        msg = f"Input the country code in a valid iso3 format (e.g. 'eth' for Ethiopia)"
        raise Exception(msg)
    
    # change to lowercase format to prevent errors

    country_code = country_code.lower()
    if len(country_code) != 3:
        msg = f"Input the country code in a valid iso3 format (e.g. 'eth' for Ethiopia)"
        raise Exception(msg)
    

    facility_gdf, country_gdf = load_market_data(country_code)

    utm_crs = facility_gdf.estimate_utm_crs()
    if not os.path.exists('./computed_centroids/'+country_code+'_centroids.geojson'):    

        # Spatial join: Finds points within the polygon
        joined_gdf = gpd.sjoin(facility_gdf.to_crs(utm_crs), country_gdf.to_crs(utm_crs), predicate="within")
        points = np.array([[point.x,point.y]  for point in joined_gdf.to_crs(utm_crs).geometry])
            # if len(points) == 0:
            #     empty_polys+=1
            #     print('Empty polygon', empty_polys)
            #     continue
        # overlap radious (15 min at walking pace of 1.4 m/s)
        ri = 1.4*15*60 
        if len(points) == 1:
            centers = points
            clusters = np.array([[points[0][0],points[0][1],0]])

        print('computing centroids ...')
        print(len(facility_gdf), 'points')
        jump_start = int(len(points)*0.2)
        if not jump_start%2:
            jump_start+=1

        first_try = True
        for i in range(jump_start,len(points)):
            if not i%10:
                print(i)
            valid, centers, clusters = centroids.validate_solution(ri, *centroids.create_clusters(i,points))
            
            if valid:
                print(i)
                # if we overshot the number of clusters we iterate backwards until finding the last valid solution
                if first_try:
                    print('First try: number of clusters is less than 20 percent of points', i)
                    first_try = False
                    for i in range(jump_start, 2, -1):
                        valid, centers_new, clusters_new = centroids.validate_solution(ri, *centroids.create_clusters(i,points))
                        if valid:
                            centers = centers_new
                            clusters = clusters_new
                        # if the result is not valid anymore we keep the last iteration
                        else:
                            break
                # if it is valid and we are not in the first try we have finished
                if not first_try:
                    break
            # if the result is not valid we keep iterating
            first_try = False
        
        centroids_gdf, facility_gdf = centroids.create_centroids_gdf(facility_gdf, centers, clusters)

        centroids_gdf.to_file('./computed_centroids/'+country_code+'_centroids.geojson')
        print('Centroids computed:', str(len(centroids_gdf))+' centroids')
    else:
        centroids_gdf = gpd.read_file('./computed_centroids/'+country_code+'_centroids.geojson')

    print('preparing friction surface to compute travel times ...')
    if tmode == 'moto':
        fs_path = '../shared_data/friction_surfaces/2020_motorized_friction_surface.geotiff'
        suffix = '_moto'
    if tmode == 'walk':
        fs_path = '../shared_data/friction_surfaces/2020_walking_only_friction_surface.geotiff'
        suffix = '_walk'
    try:
        cropped_path, fs_arr = compute_tts.crop_rast_to_country(fs_path, country_gdf, country_num=country_code, is_pop = False)
    except Exception as e:
        raise e
    # transform FS to UTM to compute TT rasters

    name, ext = os.path.splitext(fs_path)
    out_path_utm = name+'_'+country_code+'_utm'+ext
    
    compute_tts.transform_to_utm(cropped_path, out_path_utm, utm_crs)

    # Load the raster
    with rasterio.open(out_path_utm) as src:
        friction_data = src.read(1)  # Read the first band (assuming friction values)
        friction_data[friction_data<0] = np.inf
        src_transform = src.transform  # Affine transform for the raster
        # width, height = src.width, src.height  # Dimensions of the raster
        src_crs = src.crs
        print('CRS:', src_crs)
        # metadata = src.meta

    # Calculate pixel size in meters for geographic CRS
    pixel_size = compute_tts.calculate_pixel_size_in_meters(src_transform, src_crs)
    travel_times_fs_tot = []
    travel_times_osm_tot = []
    
    # pick targets whose friction pixel is below the threshold
    if tmode == 'moto':
        min_pixel_value = 0.002
    elif tmode == 'walk':
        min_pixel_value = 0.02
    else:
        raise ValueError(f"Unsupported transport mode '{tmode}'")

    # filter centroid indices by friction value at their pixel
    centroids_in_low_friction = []
    centroids_proj = centroids_gdf.geometry.to_crs(src_crs)

    for idx, geom in enumerate(centroids_proj):
        r, c = rowcol(src_transform, geom.x, geom.y)
        # guard against out-of-bounds and bad values
        if 0 <= r < friction_data.shape[0] and 0 <= c < friction_data.shape[1]:
            pix_val = friction_data[r, c]
            if not np.isnan(pix_val) and pix_val <= min_pixel_value:
                centroids_in_low_friction.append(idx)

    if not centroids_in_low_friction:
        raise ValueError(f"No centroids fall in pixels with friction ≤ {min_pixel_value}")

    H, W = fs_arr.shape  # raster height/width

    for i in tqdm(centroids_in_low_friction[0:min(100, len(centroids_in_low_friction))],
                desc = f"Computing Travel Time to {min(100, len(centroids_in_low_friction))} low-friction points"):
        n_orig = 1
        
        x, y = centroids_proj.iloc[i].x, centroids_proj.iloc[i].y
        target_row, target_col = rowcol(src_transform, x, y)

        # 10 km radius in pixels (if pixel_size is meters)
        cell_rad = int(20000 / pixel_size)
        #cell_rad = np.inf  # no radius limit, use entire raster (comment out the above line if you want to use the radius limit)
        # Clamp window bounds (CRITICAL)
        r0 = max(0, target_row - cell_rad)
        r1 = min(H, target_row + cell_rad)
        c0 = max(0, target_col - cell_rad)
        c1 = min(W, target_col + cell_rad)

        if r0 >= r1 or c0 >= c1:
            raise ValueError(f"Empty window after clamping: rows {r0}:{r1}, cols {c0}:{c1} "
                            f"for target (row={target_row}, col={target_col})")

        fs_arr_cop = fs_arr[r0:r1, c0:c1]

        mask = (~np.isnan(fs_arr_cop)) & (fs_arr_cop <= min_pixel_value)
        coords = np.argwhere(mask)  # relative to fs_arr_cop

        if coords.shape[0] < n_orig:
            # Helpful debug: how many non-NaN? what's min in window?
            non_nan = np.count_nonzero(~np.isnan(fs_arr_cop))
            min_val = np.nanmin(fs_arr_cop) if non_nan else None

            raise ValueError(
                f"Only {coords.shape[0]} pixels meet threshold {min_pixel_value}.\n"
                f"Target x,y=({x},{y}) -> (row={target_row}, col={target_col})\n"
                f"Window rows {r0}:{r1} cols {c0}:{c1} (shape={fs_arr_cop.shape})\n"
                f"non_nan={non_nan}, window_min={min_val}"
            )
        
        idx = np.random.choice(len(coords), size=n_orig, replace=False)
        # translate relative coords back to global raster indices
        random_pixels = [(r0 + coords[i][0], c0 + coords[i][1]) for i in idx]
            
        target = centroids_gdf['geometry'].to_crs(src_crs).iloc[i]
        target_coords = [target.x, target.y]

        # Generate the travel time raster using MCP.find_costs
        travel_times_fs = compute_tts.compute_OD_travel_time(friction_data, src_transform, random_pixels, target_coords, pixel_size)
        travel_times_fs_tot += travel_times_fs
        
        travel_times_osm = []

        # compute tts using the API
        # api_key = 'eyJvcmciOiI1YjNjZTM1OTc4NTExMTAwMDFjZjYyNDgiLCJpZCI6IjkwMmEwYzkwZDZkMTQ2YTVhODdkMjRmN2NlOGZiZDU2IiwiaCI6Im11cm11cjY0In0='
        api_key = 'eyJvcmciOiI1YjNjZTM1OTc4NTExMTAwMDFjZjYyNDgiLCJpZCI6IjdhNTcxNjdjMDQzMDQyZjFiYmUwZWNiYzE3ZDQ1OTA0IiwiaCI6Im11cm11cjY0In0='
        for orgin in random_pixels:
            # random_pixels are (row, col); rasterio expects (row, col) in that order
            origin_coords = rasterio.transform.xy(src_transform, orgin[0], orgin[1])
            try:
                duration = ors_drive_time_seconds(api_key, tmode, origin_coords, target_coords, epsg=32632)
                duration_s = duration['duration_s']
                travel_times_osm.append(duration_s/60)
            except Exception as e:
                print(f"Error computing travel time for origin {origin_coords} and target {target_coords}: {e}")
                travel_times_osm.append(np.nan)
                continue
        travel_times_osm_tot += travel_times_osm
    
    # Plotting the results
    print(len(travel_times_fs_tot), len(travel_times_osm_tot))
    plt.figure(figsize=(10, 6))
    plt.scatter(travel_times_fs_tot, travel_times_osm_tot, alpha=0.5)
    plt.xlabel('Travel Time from Friction Surface (minutes)', fontsize=25)
    plt.ylabel('Travel Time from OSM API (minutes)', fontsize=25)
    plt.xticks(fontsize=23)
    plt.yticks(fontsize=23)
    plt.tight_layout()
    plt.show()

    # write the results in a csv file
    results_df = pd.DataFrame({'travel_time_fs': travel_times_fs_tot, 'travel_time_osm': travel_times_osm_tot})
    results_df.to_csv('./validation_results/tt_validation_'+country_code+suffix+'.csv', index=False)    

   # finally delete the travel time rasters due to memory concerns
    #remove the friction raster utm file to avoid trash
    os.remove(out_path_utm)
    os.remove(cropped_path)
    
if __name__ == "__main__":

    parser = argparse.ArgumentParser(description="Process country data")
    parser.add_argument("country_code", type=str, help="iso3 code of the country to process")
    parser.add_argument("tmode", type=str, help="Transport mode ('moto' or 'walk')")

    args = parser.parse_args()

    main(args.country_code, args.tmode)
