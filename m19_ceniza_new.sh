#!/bin/bash
set -e  # Stop on error

INPUT_DIR="/nexus/data1/products/ceniza/input"
WORK_DIR="/nexus/data1/products/ceniza/work"
OUTPUT_BASE="/nexus/data1/products/ceniza/output"

# ==============================
#   MAIN FUNCTION
# ==============================
procesar_archivo() {
    local tgz_file="$1"
    local base_name=$(basename "$tgz_file")
    echo -e "\n=== Processing file: $base_name ==="

    # Extract year and julian day from name (pattern sYYYYJJJ)
    local time_tag=$(echo "$base_name" | grep -o "s[0-9]\{7\}" | head -1)
    local year=${time_tag:1:4}
    local jday=${time_tag:5:3}

    # Prepare output directory
    local OUT_DIR="$OUTPUT_BASE/$year/$year$jday"
    mkdir -p "$OUT_DIR"

    # Clean work directory
    if [ -d "$WORK_DIR" ]; then
        if [ "$(ls -A "$WORK_DIR")" ]; then
            echo "Cleaning work directory..."
            cd "$WORK_DIR" || exit 1
            rm -f -- * 2>/dev/null || true
        fi
    else
        mkdir -p "$WORK_DIR"
    fi

    # Move and extract
    mv "$tgz_file" "$WORK_DIR"
    cd "$WORK_DIR"

    echo "Decompressing contents..."
    tar -xvf "$base_name" >/dev/null 2>&1 || { echo "Error decompressing $base_name"; return 1; }
    rm -f "$base_name"

    # Check required files
    local req_files=("*CMIPC*.nc" "*ACTPC*.nc")
    for pattern in "${req_files[@]}"; do
        if ! ls $pattern >/dev/null 2>&1; then
            echo "Missing required files ($pattern). Skipping file $base_name."
            rm -f * || true
            return 1
        fi
    done
    echo "All required files found."

    # Optional cleanup of unneeded products
    echo "Removing unrelated products..."
    find . -type f ! -name "*CMIPC*.nc" ! -name "*AODC*.nc" ! -name "*ACTPC*.nc" -delete

    # Derive identifiers

    local sample=$(ls *CMIPC*.nc | head -1)
    local sat=$(echo "$sample" | grep -o "_G[0-9]\{2\}_" | tr -d '_')
    local mode=$(echo "$sample" | grep -o "M[0-9]" | head -1)
    local timestamp=$(echo "$sample" | grep -o "s[0-9]\{14\}" | head -1)
    local ceniza="CG_ABI-L2-ASH-${mode}_${sat}_${timestamp}"
    echo "Output folder: $OUT_DIR"
    echo "Base name: $ceniza"

    # ==========================
    #  PROCESSING BLOCK
    # ==========================

    # Convert NC to TDF
    for f in *CMIPC*.nc *AODC*.nc *ACTPC*.nc; do
        nctdf include_vars= "$f" "${f}.tdf"
    done
    echo "NC to TDF conversion done."

    # Load required channels
    ch01=$(ls $WORK_DIR/*C01*.tdf)
    ch02=$(ls $WORK_DIR/*C02*.tdf)
    ch03=$(ls $WORK_DIR/*C03*.tdf)
    ch04=$(ls $WORK_DIR/*C04*.tdf)
    ch07=$(ls $WORK_DIR/*C07*.tdf)
    ch11=$(ls $WORK_DIR/*C11*.tdf)
    ch13=$(ls $WORK_DIR/*C13*.tdf)
    ch14=$(ls $WORK_DIR/*C14*.tdf)
    ch15=$(ls $WORK_DIR/*C15*.tdf)
    mask=$(ls $WORK_DIR/*ACTPC*.tdf)

    # Sun Zenith
    angles \
        latitude='no' \
	longitude='no' \
	sat_zenith='no' \
	sun_zenith='yes' \
        scatter_phase='no' \
	sun_reflection='no' \
	rel_azimuth='no' \
        store_cosines='no' \
	real_output='yes' \
	poly_size='100' \
	$ch15

    echo "Sun Zenith done."

    # Inverse transmissivity

    emathp \
        file1_vars='CMI' \
        file2_vars='CMI' \
        file3_vars='CMI' \
        file4_vars='CMI' \
        file5_vars='CMI' \
        file6_vars='CMI sun_zenith' \
        num_exprs='3' \
        y1_expr='x4 - x6' \
        y2_expr='x3 - x4' \
        y3_expr='x2 - x4' \
        save_exprs='1 2 3' \
        var_names='B13-B15 B11-B13 B07-B13' \
        var_units='- - -' \
        var_types='float float float' \
        $ch04 \
        $ch07 \
        $ch11 \
        $ch13 \
        $ch14 \
        $ch15 \
        $ceniza.trans

    echo "Inverse transmissivity done."

    # Nhood
    nhood \
        reduce='no' \
        box_sides='5 5' \
        min_good='3' \
        expr_vars='B13-B15 B11-B13' \
        expression='x1 < 0 && (x1-(ave(x1)+(stdev(x1)))) < -1 ? 1 : x1 < 1 && (x1-(ave(x1)+(stdev(x1)))) < -1 ? 2 : 0' \
        var_name='nhood_B14_B15' \
        var_units= \
        var_type='float' \
        $ceniza.trans \
        $ceniza.nhood

    echo "Nhood done."

    # Ash detection

    emathp \
        file1_vars='B13-B15 B11-B13 B07-B13' \
        file2_vars='nhood_B14_B15' \
        file3_vars='CMI' \
        file4_vars='CMI' \
        file5_vars='CMI sun_zenith' \
        file6_vars='Phase' \
        num_exprs='7' \
        y1_expr='x1 < 0 && x2 > 0 && x3 > 2 || x4 == 1 ? 1 : x1 < 1 && x2 > -0.5 && x3 > 2 || x4 == 2 ? 2 : 0' \
        y2_expr='x1 < 0 && x2 > 0 && x3 > 2 || x4 == 1 ? 1 : x1 < 1 && x2 > -0.5 && x3 > 2 && x5 > 0.002 && x6 < 273 || x4 == 2 ? 2 : 0' \
        y3_expr='x1 < 0 && x2 > 0 && x3 > 2 && x5 > 0.002 || x4 == 1 ? 1 : x1 < 1 && x2 > -0.5 && x3 > 2 && x5 > 0.002 || x4 == 2 ? 2 : 0' \
        y4_expr='x8 > 85 ? y1 : x8 < 85 && x8 > 70 ? y2 : x8 < 70 ? y3 : 0' \
        y5_expr='y4 == 1 ? y4 : y4 == 2 && x2 >= -0.6 ? 2 : y4 == 2 && x2 >= -1 ? 2 : y4 == 2 && x2 >= -1.5 ? 3 : y4 == 2 && x2 < -1.5 ? 0 : y4' \
        y6_expr='y5 <= 2 && x3 <= 0 ? 0 : y5 >= 3 && x3 <= 1.5 ? 0 : y5' \
        y7_expr='y6 == 2 && x9 == 1 ? 4 : y6 == 2 && x9 == 4 ? 0 : y6 == 3 && x9 == 1 ? 5 : y6 == 3 && x9 >= 2 ? 0 : y6' \
        save_exprs='1^7' \
        var_names='CENIZA_N CENIZA_CREP CENIZA_D CENIZA_TIEMPO CENIZA_UM1 CENIZA_UM2 CENIZA' \
        var_units='- - - - - - -' \
        var_types='float float float float float float float' \
        $ceniza.trans \
        $ceniza.nhood \
        $ch04 \
        $ch14 \
        $ch15 \
        $mask \
        $ceniza.tv

    echo "Ash detection done."

    # Crop and export
    fastreg2 \
        sensor_resol='yes' \
        unit_size='0' \
        equal_scales='yes' \
        master_file='/opt/terascan/pass/masters/cenizas_1km' \
        master_var= \
        include_vars= \
        brute_force='no' \
        poly_size='100' \
        interpolate='nn' \
        off_protect='no' \
        whole_input='no' \
        $ceniza.tv \
        $ceniza.tv.Popo

    echo "CONUS Crop"

    expgeotiff \
        include_vars='CENIZA' \
        sort_by_line= \
        apply_scaling='yes' \
        trans_matrix='no' \
        force_unsigned='no' \
        add_offset='yes' \
        geo_datum_code='6326' \
        $ceniza.tv.Popo \
        $ceniza.Popo.tif

    echo "GeoTIFF exported."

    # Copy final results
    find "$WORK_DIR" -maxdepth 1 -type f \( -name "*.tif" -o -name "*.tdf" -o -name "*ASH*" \) -exec cp {} "$OUT_DIR" \;

    # Safe cleanup
    if [ "$PWD" == "$WORK_DIR" ]; then
        find "$WORK_DIR" -type f ! \( -name "*.tif" -o -name "*.tdf" \) -delete
    fi

    echo "Processing completed for $base_name."
}

# ==============================
#   MAIN LOOP
# ==============================
echo "===== START MASS PROCESSING ====="
if [ ! -d "$INPUT_DIR" ] || [ -z "$(ls -A "$INPUT_DIR")" ]; then
    echo "No files found in $INPUT_DIR"
    exit 1
fi

for tgz_file in $(ls -t "$INPUT_DIR"/*.tgz 2>/dev/null); do
    procesar_archivo "$tgz_file"
done

echo "===== ALL FILES PROCESSED ====="

