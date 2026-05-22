#!/bin/bash

DISK_ADM_PATH=/data/fast/fmalveiro/gadm/raw/national/KEN/adm0/gadm41_KEN_0.json.zip
DISK_FACILITIES_PATH=/data/shared/fmalveiro/hdx/health_facilities_ssa/processed/national/KEN/KEN-hospitals.geojson
DISK_WFRICTION_PATH=/data/big/fmalveiro/malariaatlas/raw/2020_walking_only_friction_surface.zip
DISK_MFRICTION_PATH=/data/big/fmalveiro/malariaatlas/raw/2020_motorized_friction_surface.zip


DIR_ADM=./data/raw/adm/
DIR_FACILITIES=./data/raw/facilities/
DIR_FRICTION=./data/raw/friction/


FILE_ADM=adm.zip
FILE_FACILITIES=ken-facilities.geojson
FILE_WFRICTION=walking.zip
FILE_MFRICTION=motorised.zip


PROJ_ADM_PATH=${DIR_ADM}${FILE_ADM}
PROJ_FACILITIES_PATH=${DIR_FACILITIES}${FILE_FACILITIES}
PROJ_WFRICTION_PATH=${DIR_FRICTION}${FILE_WFRICTION}
PROJ_MFRICTION_PATH=${DIR_FRICTION}${FILE_MFRICTION}

mkdir -p ${DIR_ADM}
mkdir -p ${DIR_FACILITIES}
mkdir -p ${DIR_FRICTION}


ln -s ${DISK_ADM_PATH} ${PROJ_ADM_PATH}
 
ln -s ${DISK_FACILITIES_PATH} ${PROJ_FACILITIES_PATH}

ln -s ${DISK_WFRICTION_PATH} ${PROJ_WFRICTION_PATH}
ln -s ${DISK_MFRICTION_PATH} ${PROJ_MFRICTION_PATH}




#CONFIGFILE='config/datasets.json'
#
#jq -r '.datasets[] | "\(.path) \(.symlink)"' "${CONFIGFILE}" | \
#while read src dst; do
#	mkdir -p "${dst}"
#	ln -snf "${src}" "${dst}"
#done

