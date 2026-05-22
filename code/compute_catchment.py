"""

Robert's code was called with 
    python compute_accessibilities.py 'ken' '30' 'moto'

Created files



Those files are used here to make catchment polygons.

Call with:
python ~/extra/robert-fork/code/compute_catchment.py 'epsg:4326' 'epsg:21097' code/computed_acc/ken/ closest_moto_fac.tif adm_loaddir adm_loadfile savedir savefile
"""
import geopandas as gpd
import geocube.vector
import rioxarray
import rasterio

import subprocess
import argparse
import time
import sys
import os



def argparser():
    parser = argparse.ArgumentParser(
                    prog=sys.argv[0],
                    description='What the program does',
                    epilog='Text at the bottom of help'
    )

    parser.add_argument('from_crs')
    parser.add_argument('to_crs')

    parser.add_argument('country_gid')
    parser.add_argument('threshold')
    parser.add_argument('transport')

    parser.add_argument('tif_loaddir')
    parser.add_argument('tif_loadfile')

    parser.add_argument('adm_loaddir')
    parser.add_argument('adm_loadfile')

    parser.add_argument('facility_loaddir')
    parser.add_argument('facility_loadfile')

    parser.add_argument('savedir')
    parser.add_argument('savefile')

    parser.add_argument('--script_path', default='./code/compute_accessibilities.py')


    return parser



def load_geodataframe(loaddir, loadfile):
    return gpd.read_file(os.path.join(loaddir, loadfile))


def save_geodataframe(gdf, savedir, savefile):
    os.makedirs(savedir, exist_ok=True)
    return gdf.to_file(os.path.join(savedir, savefile))


def project(element, crs):
    return element.to_crs(crs)


def compute_friction_surface(country_gid, v_threshold, transport, facility_loadpath, script_path):
    """
    ken 30 moto
    """
    command = f"python {script_path} {country_gid} {v_threshold} {transport} {facility_loadpath}"
    output = subprocess.check_output(command, shell=True)
    
    print(output.decode('utf-8'))
    return True


def clip_geometry(gdf, clipping):
    return gdf.clip(clipping)


def vectorise(tif_loadpath, adm_gdf):

    data = rioxarray.open_rasterio(tif_loadpath, mask_and_scale=True).squeeze().astype('float32')
    data.name = 'idx'

    gdf = geocube.vector.vectorize(data)

    data.close()
    

    assert adm_gdf.crs.is_projected
    proj_gdf = project(gdf, adm_gdf.crs)

    proj_gdf = clip_geometry(proj_gdf, adm_gdf)

    proj_gdf = proj_gdf.set_index(data.name).sort_index(ascending=True)
    print(proj_gdf)
    input('projgdf')
    return proj_gdf



def main(args):
    from_crs = args.from_crs
    to_crs = args.to_crs
    
    country_gid = args.country_gid
    threshold = args.threshold
    transport = args.transport

    tif_loaddir = args.tif_loaddir
    tif_loadfile = args.tif_loadfile
    
    adm_loaddir = args.adm_loaddir
    adm_loadfile = args.adm_loadfile

    facility_loaddir = args.facility_loaddir
    facility_loadfile = args.facility_loadfile
    
    savedir = args.savedir
    savefile = args.savefile

    script_path = args.script_path

    
    start_time = time.time()

    tif_loadpath = os.path.join(tif_loaddir, tif_loadfile)

    print('Computing friction surfaces...')
    compute_friction_surface(country_gid, threshold, transport, os.path.join(facility_loaddir, facility_loadfile), script_path)
    print('Finished computing accessibilities.')

    
    adm_gdf = load_geodataframe(adm_loaddir, adm_loadfile)
    proj_adm = project(adm_gdf, to_crs)

    print('Vectorising...')
    proj_polygons = vectorise(tif_loadpath, proj_adm)

    polygons_gdf = project(proj_polygons, from_crs)

    print('Saving...')
    save_geodataframe(polygons_gdf, savedir, savefile)


    end_time = time.time()
    print(f'The program took {end_time - start_time} seconds.')


    return



if __name__ == '__main__':
    parser = argparser()
    args = parser.parse_args()
    main(args)
