#!/bin/bash

PYTHON=python

SCRIPT_CATCHMENT=./code/compute_catchment.py


SRC_CRS='epsg:4326'
TGT_CRS='epsg:21097'

ISO3='ken'

SPEED=30
MODE='moto'

TT_DIR=computed_acc/ken/
TT_FILE=closest_moto_fac.tif

ADM_DIR=/data/shared/fmalveiro/gadm/raw/KEN/
ADM_FILE=gadm41_KEN_0.json

FAC_DIR=/data/shared/fmalveiro/lagrange/output/FL20240426KEN/PL_20240505_FloodExtent_Garissa/
FAC_FILE=facilities.geojson

CATCHMENT_DIR=/data/shared/fmalveiro/robert/processed/
CATCHMENT_FILE=ken-catchment-facility.geojson


USE_CONDA=true
CONDA_PATH=$(whereis conda | awk '{print $2}')
CONDA_RUN="run -n"
ENV_NAME=baseline_assessment

RUN="${PYTHON} ${SCRIPT_CATCHMENT} ${SRC_CRS} ${TGT_CRS} ${ISO3} ${SPEED} ${MODE} ${TT_DIR} ${TT_FILE} ${ADM_DIR} ${ADM_FILE} ${FAC_DIR} ${FAC_FILE} ${CATCHMENT_DIR} ${CATCHMENT_FILE}"


if ${USE_CONDA}; then
  ${CONDA_PATH} ${CONDA_RUN} ${ENV_NAME} ${RUN}

else
	${RUN}
fi

