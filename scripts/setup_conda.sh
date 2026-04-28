#!/bin/bash

CONDA_PATH="/home/fmalveiro/anaconda3/condabin/conda"
UPDATE="env update -f"
CONFIG_FILE="config/environment.yml"


${CONDA_PATH} ${UPDATE} ${CONFIG_FILE}

