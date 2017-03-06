#!/bin/bash

participant_label=$1

echo "running: docker run -i --name $participant_label \
  -v /data/jflournoy/rockland/:/bids_dataset:ro \
  -v /data/jflournoy/rockland/derivatives/:/outputs \
  bids/freesurfer /bids_dataset /outputs \
  participant --participant_label $participant_label \
  --license_key `cat ~/freesurfer.lic`" 

docker run -i --name $participant_label \
  -v /data/jflournoy/rockland/:/bids_dataset:ro \
  -v /data/jflournoy/rockland/derivatives/:/outputs \
  bids/freesurfer /bids_dataset /outputs \
  participant --participant_label $participant_label \
  --license_key `cat ~/freesurfer.lic` 

