import geopandas as gpd
import pandas as pd
import numpy as np
import argparse
import rasterio
import pickle
import shutil
import scipy
import tqdm

import pathlib
import sys
import os


# import shapely
# from shapely.geometry import Polygon, MultiPolygon, Point, mapping

# local files

# import centroids 
import compute_tts
import accessibility_metrics
# codes for the countries are taken from openAfrica's dataset (https://open.africa/dataset/africa-shapefiles/resource/dcdadd25-0137-4c93-ae5a-82b39d424d60)



def argparser():
    parser = argparse.ArgumentParser(
                    prog=sys.argv[0],
                    description='Process country data',
                    epilog='Text at the bottom of help'
    )

    parser.add_argument('from_crs')
    parser.add_argument('to_crs')

    parser.add_argument('country_code', type=str, help='iso3 code of the country to process')
    parser.add_argument('threshold', type=str, help='threshold travel time for pure cumulative accessibility')
    parser.add_argument('tmode', type=str, help="Transport mode ('moto' or 'walk')")

    parser.add_argument('facility_loadpath', type=str, help='Filepath with facilities')
    parser.add_argument('aoi_loadpath', type=str, help='Filepath with area of interest (country)')
    parser.add_argument('friction_loadpath', type=str, help='Filepath with friction surface')

    parser.add_argument('tt_savepath', type=str, help='Filepath where to save travel time friction surface')

    return parser



def load_facility_data(facility_path:str, aoi_path:str):

    print(f"Loading facility data from {facility_path}...")
    facility_gdf = gpd.read_file(facility_path)
    print('Number of facilities fron dataset:', len(facility_gdf))

    
    crs = facility_gdf.crs
    utm_crs = facility_gdf.estimate_utm_crs()

    facility_gdf = facility_gdf.to_crs(utm_crs)


    # remove empty geometry entries
    n_empty = pd.isna(facility_gdf['geometry']).sum()
    print(f"There are {n_empty}/{facility_gdf.shape[0]} empty geometry entries. Dropping...")
    facility_gdf = facility_gdf.dropna(subset='geometry').reset_index(drop=True)
    
    # get centroids if facilities are polygons
    facility_gdf['geometry'] = facility_gdf['geometry'].centroid
    facility_gdf = facility_gdf.to_crs(crs)



    country_borders = gpd.read_file(aoi_path)
    country_borders = country_borders.to_crs(utm_crs)


    facility_gdf = facility_gdf.to_crs(utm_crs)
    facility_points_x = np.array([point.x for point in facility_gdf['geometry']])
    facility_points_y = np.array([point.y for point in facility_gdf['geometry']])

    facility_gdf = facility_gdf.to_crs(crs)
    

    facility_gdf = facility_gdf.reset_index(drop=False).rename({'index': 'ID'}, axis=1)
    
    facility_gdf = facility_gdf.to_crs(utm_crs).sjoin(country_borders.to_crs(utm_crs), how='left')

    facility_gdf = facility_gdf.to_crs(crs)
    facility_gdf = facility_gdf.reset_index(drop=True)

    facility_gdf['ID'] = facility_gdf.index
    
    facility_gdf = facility_gdf[['ID', 'geometry']]

    
    print('Total number of points', facility_gdf.shape[0])
    #print('Number of overlapping points at less than {0}m:'.format(overlap_rad), len(same_points))


    return (facility_gdf, country_borders.to_crs(crs))


# Adding colorbars
def fmt(x, pos):
    a, b = '{:.1e}'.format(x).split('e')
    b = int(b)
    if x!=0:
        return r'${} \times 10^{{{}}}$'.format(a, b)
    else:
        return '0'
    


def main(args):

    country_code = args.country_code
    threshold = args.threshold
    tmode = args.tmode

    facility_loadpath = args.facility_loadpath
    aoi_loadpath = args.aoi_loadpath
    friction_loadpath = args.friction_loadpath

    tt_savepath = args.tt_savepath
    
    
    if tmode != 'moto' and tmode != "walk":
        msg = f"Choose a valid transport mode. Options walk for walking and moto for motorised. {tmode} is not valid"
        raise ValueError(msg)
    try:
        threshold = float(threshold)
    except:
        print("Provide the threshold as a number in string format (e.g., '60')")
        return

    
    # change to lowercase format to prevent errors
    country_code = country_code.lower()
    if len(country_code) != 3:
        msg = 'Input the country code in a valid iso3 format (e.g. "eth" for Ethiopia)'
        raise ValueError(msg)

    print(f"Loading facility and adm data from {facility_loadpath} and {aoi_loadpath}...")

    facility_gdf, country_gdf = load_facility_data(facility_loadpath, aoi_loadpath)

    
    utm_crs = facility_gdf.estimate_utm_crs()

    
    centroids_gdf = facility_gdf[['ID', 'geometry']]
    assert centroids_gdf['geometry'].map(lambda x: x.geom_type == 'Point').all()


    # Loading Friction Surface
    print('Preparing friction surface to compute travel times ...')
    #if tmode == 'moto':
    #    fs_path = '../shared_data/friction_surfaces/2020_motorized_friction_surface.geotiff'
    #    suffix = '_moto'
    #if tmode == 'walk':
    #    fs_path = '../shared_data/friction_surfaces/2020_walking_only_friction_surface.geotiff'
    #    suffix = '_walk'

    suffix = '_' + tmode
    
    fs_path = friction_loadpath
    
    cropped_path = fs_path.replace('raw', 'processed')
    cropped_filepath = pathlib.Path(cropped_path.replace('zip://', ''))
    cropped_file = f"{country_code}-{cropped_filepath.stem}{cropped_filepath.suffix}"

    cropped_path = f"zip://{os.path.join(cropped_filepath.parent, cropped_file)}"
                                               
    try:      
        cropped_path, fs_arr = compute_tts.crop_rast_to_country(fs_path, country_gdf, country_code, cropped_path, is_pop = False)
    except Exception as e:
        raise e
    
    # transform FS to UTM to compute TT rasters

    #name, ext = os.path.splitext(fs_path)
    #out_path_utm = name+'_'+country_code+'_utm'+ext


    out_file_utm = f"{country_code}-{cropped_filepath.stem}_utm{cropped_filepath.suffix}"
    out_path_utm = f"zip://{os.path.join(cropped_filepath.parent, out_file_utm)}"
    
    
    compute_tts.transform_to_utm(cropped_path, out_path_utm, utm_crs)

    # File path to the friction raster
    root_dest = './computed_tts/'
    dest_path = root_dest+country_code

    
        # Compute travel times if they have not been computed for this country
    if not os.path.exists(root_dest): 
        os.mkdir(root_dest)

    if not os.path.exists(dest_path): 
        os.mkdir(dest_path)
        # Load the raster
        with rasterio.open(out_path_utm) as src:
            friction_data = src.read(1)  # Read the first band (assuming friction values)
            friction_data[friction_data<0] = np.inf
            src_transform = src.transform  # Affine transform for the raster
            # width, height = src.width, src.height  # Dimensions of the raster
            src_crs = src.crs
            # metadata = src.meta

        # Calculate pixel size in meters for geographic CRS
        pixel_size = compute_tts.calculate_pixel_size_in_meters(src_transform, src_crs)


        # Target dimensions (known height and width)
        target_width = fs_arr.shape[1]  
        target_height = fs_arr.shape[0] 
        fs_src = rasterio.open(cropped_path)
        dst_transform = fs_src.transform
        dst_crs = fs_src.crs
        fs_src.close()
        for i in tqdm.tqdm(range(len(centroids_gdf)), desc = "Computing Travel Time Rasters"):
            
            # if i%100==0:
            #     print(i)
            target = centroids_gdf['geometry'].to_crs(src_crs).iloc[i]
            target_coords = [target.x, target.y]
            ID = centroids_gdf.ID.iloc[i]
            # Generate the travel time raster using MCP.find_costs
            travel_time_raster = compute_tts.generate_travel_time_raster(friction_data, src_transform, target_coords, pixel_size)

            # Transform, and CRS in UTM
            reprojected_array = compute_tts.reproject_to_geographic(travel_time_raster, src_transform, 
                                                        src_crs, dst_crs, target_width, 
                                                        target_height, dst_transform)
            

            # Save the result to a GeoTIFF
            with rasterio.open(dest_path+'/'+str(ID)+'.tif',
                "w",
                driver="GTiff",
                height=target_height,
                width=target_width,
                count=1,
                dtype=reprojected_array.dtype,
                crs=dst_crs,
                transform=dst_transform) as dst:
            
                dst.write(reprojected_array, 1)

    else:
        print(f'Travel time rasters already computed for country {country_code}')

    '''COMPUTING ACCESSIBIITIES'''

    R = 60 # min
    beta = -np.log(0.01)/R # accessibility = 0.01 when r = 60 min
    tt_dir = dest_path+'/'

    # print('Computing Gravity Acc.')
    # access_mat = accessibility_metrics.compute_grav_acc(beta, pop_arr, tt_dir)
    
    # print('Computing Cumulative Acc.')
    # access_mat_cumul =  accessibility_metrics.compute_grav_acc_cumul(threshold, fs_arr, tt_dir)

    #print('Computing Pure Cumulative Acc.')
    #access_mat_pure_cumul =  accessibility_metrics.compute_cumulative(threshold, fs_arr, tt_dir)

    # print('Computing Entropy')
    # entropy, mean_dist = accessibility_metrics.compute_entropy_acc(beta, fs_arr, tt_dir)

    #print('Computing Mod Entropy with 4h upper bound')
    #entropy_mod = accessibility_metrics.compute_mod_entropy_acc(beta, fs_arr, tt_dir, 4*60)

 
    print('Computing Shortest TT.')
    shortest_tt_rast = accessibility_metrics.shortest_travel_time(tt_dir)

    # print('max tt', np.nanmax(shortest_tt_rast))
    '''SAVING ACCESSIBIITIES'''

    if not os.path.exists('./computed_acc/'+country_code): 
        os.makedirs('./computed_acc/'+country_code)


    # mod_en_path = './computed_acc/'+country_code+f'/entropy_mod_4h{suffix}.tif'


    shortest_tt_path = tt_savepath
    #shortest_tt_path = './computed_acc/'+country_code+f'/shortest{suffix}_tt.tif'
    # acc_path_pure_cumul = './computed_acc/'+country_code+f'/acc_pure_cumul{suffix}.tif'
    
    fs_src = rasterio.open(cropped_path)
    dst_transform = fs_src.transform
    dst_crs = fs_src.crs
    fs_src.close()
    # Write the entropy 
    
    #with rasterio.open(mod_en_path,"w",driver="GTiff", height=entropy_mod.shape[0],
    #                   width=entropy_mod.shape[1], count=1, dtype=entropy_mod.dtype,
    #                   crs=dst_crs, transform=dst_transform) as dst:
    #    
    #    dst.write_band(1, entropy_mod) 

    # Write the travel time 

    print(f"Writing shortest tt to {shortest_tt_path}...")
    
    with rasterio.open(shortest_tt_path,"w",driver="GTiff", height=shortest_tt_rast.shape[0],
                       width=shortest_tt_rast.shape[1], count=1, dtype=shortest_tt_rast.dtype,
                       crs=dst_crs, transform=dst_transform) as dst:
        
        dst.write_band(1, shortest_tt_rast) 

    # Write the cumulative 

    #with rasterio.open(acc_path_pure_cumul,"w",driver="GTiff", height=access_mat_pure_cumul.shape[0],
    #                   width=access_mat_pure_cumul.shape[1], count=1, dtype=access_mat_pure_cumul.dtype,
    #                   crs=dst_crs, transform=dst_transform) as dst:
#
    #    dst.write_band(1, access_mat_pure_cumul) 
        
    # finally delete the travel time rasters due to memory concerns
    #remove the friction raster utm file to avoid trash
    #os.remove(out_path_utm)
    #os.remove(cropped_path)
    shutil.rmtree(tt_dir)
    return



if __name__ == '__main__':
    parser = argparser()
    args = parser.parse_args()
    main(args)
