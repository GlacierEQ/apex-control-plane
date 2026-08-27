#!/usr/bin/env bash

oci compute instance launch \
  --compartment-id "ocid1.tenancy.oc1..aaaaaaaa6arela2mprzl3oyfgn7ltrdm2prgezybmfkxp4xjnazeie6vahhq" \
  --shape "VM.Standard.A1.Flex" \
  --shape-config '{"ocpus": 4, "memoryInGBs": 24}' \
  --display-name "apex-temporal-sovereign-head" \
  --region "mx-monterrey-1" \
  --user-data-file "/Users/kcbflux/APEX_SYSTEM/INFRASTRUCTURE/apex-control-plane/infrastructure/oci/cloud_init_temporal.sh" \
  --assign-public-ip true
