#!/bin/bash
# organize_media.sh (Improved)

# set -euo pipefail  # Uncomment if you want the script to exit on any error

##############################################################################
# CONFIGURATION
##############################################################################
DRY_RUN=false
PARALLEL_JOBS=1  # Number of parallel jobs
PROGRESS_FILE="/tmp/media_organizer_progress"
echo 0 > "$PROGRESS_FILE" # Initialize progress counter

show_help() {
  echo "Usage: $0 [OPTIONS]"
  echo ""
  echo "Options:"
  echo "  --source <dir>      Specify the source directory containing media files"
  echo "  --target <dir>      Specify the target directory for organized media files"
  echo "  --dry-run           Simulate file moves without actually executing them"
  echo "  --parallel <jobs>   Number of parallel processes to use (default: 4)"
  echo "  --help              Display this help message and exit"
  exit 0
}

while [[ "$#" -gt 0 ]]; do
  case "$1" in
    --dry-run)
      DRY_RUN=true
      shift
      ;;
    --source)
      SOURCE_DIR="$2"
      shift 2
      ;;
    --target)
      TARGET_DIR="$2"
      shift 2
      ;;
    --parallel)
      PARALLEL_JOBS="$2"
      shift 2
      ;;
    --help)
      show_help
      ;;
    *)
      echo "Unknown option: $1"
      exit 1
      ;;
  esac
done

if [[ -z "$SOURCE_DIR" || -z "$TARGET_DIR" ]]; then
  echo "Missing required arguments. Use --help for usage information."
  exit 1
fi

LOG_DIR="/var/log/media_organization"
CURRENT_DATE=$(date +"%Y-%m-%d_%H%M%S")

# Initialize counters
TOTAL_FILES=0
DUPLICATES=0
ERRORS=0

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

##############################################################################
# PREPARATION
##############################################################################
mkdir -p "$LOG_DIR"
mkdir -p "$TARGET_DIR"

IFS=$'\n' # Handle spaces in filenames
shopt -s nocaseglob

echo -e "${YELLOW}=== Media Organization Started: $(date) ===${NC}"
echo -e "Source: ${YELLOW}${SOURCE_DIR}${NC}"
echo -e "Target: ${YELLOW}${TARGET_DIR}${NC}"
echo -e "Logs:   ${YELLOW}${LOG_DIR}/${CURRENT_DATE}_*.log${NC}"
echo "------------------------------------------------"

# Collect eligible files
# mapfile -t MEDIA_FILES < <(find "$SOURCE_DIR" -type f \( \
#   -iname "*.3gp" -o -iname "*.avi" -o -iname "*.mov" -o -iname "*.mp4" -o \
#   -iname "*.mpg" -o -iname "*.wmv" -o -iname "*.jpg" -o -iname "*.jpeg" -o \
#   -iname "*.png" -o -iname "*.gif" \) 2>/dev/null)
mapfile -d '' -t MEDIA_FILES < <(find "$SOURCE_DIR" -type f \( \
  -iname "*.3gp" -o -iname "*.avi" -o -iname "*.mov" -o -iname "*.mp4" -o \
  -iname "*.mpg" -o -iname "*.wmv" -o -iname "*.jpg" -o -iname "*.jpeg" -o \
  -iname "*.png" -o -iname "*.gif" \) -print0 2>/dev/null)
TOTAL_FILES=${#MEDIA_FILES[@]}
echo -e " ${GREEN}Found ${TOTAL_FILES} media files${NC}"
# for file in "${MEDIA_FILES[@]}"; do
#  echo "$file"
# done

##############################################################################
# FUNCTION FOR PROGRESS TRACKING
##############################################################################
update_progress() {
  local count
  count=$(< "$PROGRESS_FILE")  # Read current count
  count=$((count + 1))         # Increment count
  echo "$count" > "${PROGRESS_FILE}.tmp"  # Write to temp file
  mv "${PROGRESS_FILE}.tmp" "$PROGRESS_FILE"  # Atomic update

  # Ensure percentage is calculated correctly
  local percent=$((count * 100 / TOTAL_FILES))

  # Force output refresh
  printf "\\rProcessing: %d/%d [%d%%]  " "$count" "$TOTAL_FILES" "$percent" > /dev/tty
}

##############################################################################
# MAIN PROCESS (Parallelized)
##############################################################################
process_file() {
  local file="$1"
  
  filename=$(basename "$file")
  ext=$(echo "${file##*.}" | tr '[:upper:]' '[:lower:]')

  META=$(exiftool -api QuickTimeUTC=1 \
                  -d '%Y:%m:%d %Y%m%d-%H%M%S' \
                  -DateTimeOriginal -CreateDate -MediaCreateDate -TrackCreateDate -FileModifyDate \
                  "$file" 2>/dev/null || echo "ExiftoolError")
  if [[ "$META" == "ExiftoolError" ]]; then
    echo -e "\n${RED}ERROR:${NC} Exiftool failed for $file" | tee -a "${LOG_DIR}/${CURRENT_DATE}_errors.log"
    return
  fi

  DIR_DATE=$(echo "$META" | awk -F': ' '/Date\/Time Original|Create Date|Media Create Date|Track Create Date|File Modify Date/ {if ($2 ~ /^[0-9]{4}:[0-9]{2}:[0-9]{2}/) {print $2; exit;}}')
  if [[ -z "$DIR_DATE" ]]; then
    DIR_DATE=$(stat -c "%y" "$file" | awk '{print $1}' | sed 's/-/:/g')
  fi
  YEAR=$(echo "$DIR_DATE" | cut -d: -f1)
  MONTH=$(echo "$DIR_DATE" | cut -d: -f2)
  [[ -z "$YEAR" ]] && YEAR="unknown"
  [[ -z "$MONTH" ]] && MONTH="unknown"

  FINAL_DIR="${TARGET_DIR}/${YEAR}/${MONTH}"
  mkdir -p "$FINAL_DIR"

  FILE_TIMESTAMP=$(date -r "$file" "+%Y%m%d-%H%M%S")
  ORIG_BASE=$(basename "$file" ."$ext" | tr -cd '[:alnum:]_-')
  ORIG_BASE="${ORIG_BASE:0:20}"
  NEW_NAME="${FILE_TIMESTAMP}_${ORIG_BASE}.${ext}"

  if [[ "$DRY_RUN" == true ]]; then
    echo "Would move: $file -> ${FINAL_DIR}/${NEW_NAME}"
  else
    mv -v "$file" "${FINAL_DIR}/${NEW_NAME}" >> "${LOG_DIR}/${CURRENT_DATE}_moves.log" 2>&1
  fi
  
  update_progress
}

export -f process_file update_progress
export TARGET_DIR DRY_RUN LOG_DIR CURRENT_DATE TOTAL_FILES PROGRESS_FILE


echo "Processing files in parallel with $PARALLEL_JOBS jobs..."
# printf "%s\n" "${MEDIA_FILES[@]}" | xargs -I {} -P "$PARALLEL_JOBS" bash -c 'process_file "$@"' _ {}
printf "%s\0" "${MEDIA_FILES[@]}" | xargs -0 -P "$PARALLEL_JOBS" -I {} bash -c 'process_file "$@"' _ "{}"
# find "$SOURCE_DIR" -type f \( \
#   -iname "*.3gp" -o -iname "*.avi" -o -iname "*.mov" -o -iname "*.mp4" -o \
#   -iname "*.mpg" -o -iname "*.wmv" -o -iname "*.jpg" -o -iname "*.jpeg" -o \
#   -iname "*.png" -o -iname "*.gif" \) -print0 | xargs -0 -P "$PARALLEL_JOBS" -I {} bash -c 'process_file "$@"' _ {}

##############################################################################
# FINAL SUMMARY
##############################################################################
echo -e "\n\n${YELLOW}=== Media Organization Finished: $(date) ===${NC}"