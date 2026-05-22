#!/bin/bash

PYTHON='python -u'

SCRIPT_CATCHMENT=./src/compute_catchment.py


FROM_CRS='epsg:4326'
TO_CRS='epsg:21097'

ISO3='ken'

SPEED=30
MODE='moto'

TT_DIR=computed_acc/ken/
TT_FILE=closest_moto_fac.tif

ADM_DIR='zip://data/raw/adm/'
ADM_FILE='adm.zip!gadm41_KEN_0.json'

FAC_DIR='data/raw/facilities/health/'
FAC_FILE='ken-facilities.geojson'

FRICTION_DIR='zip://data/raw/friction/'
FRICTION_FILE='motorised.zip!2020_motorized_friction_surface.geotiff'

TT_DIR='/data/big/fmalveiro/lagrange/data/'
TT_FILE='ken-tt-facility.tif'

LN_TT_DIR='results/output/'
LN_TT_FILE='ken-tt-facility.tif'


CATCHMENT_DIR='results/output/'
CATCHMENT_FILE='ken-catchment-facility.geojson'


ADM_PATH=${ADM_DIR}${ADM_FILE}
FAC_PATH=${FAC_DIR}${FAC_FILE}
FRICTION_PATH=${FRICTION_DIR}${FRICTION_FILE}
TT_PATH=${TT_DIR}${TT_FILE}
CATCHMENT_PATH=${CATCHMENT_DIR}${CATCHMENT_FILE}

LN_TT_PATH=${LN_TT_DIR}${LN_TT_FILE}



USE_CONDA=true
CONDA_PATH=$(whereis conda | awk '{print $2}')
CONDA_RUN="run -n"
ENV_NAME=baseline_assessment



# from_crs to_crs country_gid threshold transport tif_loaddir tif_loadfile adm_loaddir adm_loadfile facility_loaddir facility_loadfile  friction_loaddir friction_loadfile savedir savefile

RUN="${PYTHON} ${SCRIPT_CATCHMENT} ${FROM_CRS} ${TO_CRS} ${ISO3} ${SPEED} ${MODE} ${ADM_PATH} ${FAC_PATH} ${FRICTION_PATH} ${TT_PATH} ${CATCHMENT_PATH}"

rm data/processed/friction/ken-motorised.zip 
rm -r computed_tts/ken/

if ${USE_CONDA}; then
  ${CONDA_PATH} ${CONDA_RUN} ${ENV_NAME} ${RUN}

else
	${RUN}
fi

ln -s ${TT_PATH} ${LN_TT_PATH}


