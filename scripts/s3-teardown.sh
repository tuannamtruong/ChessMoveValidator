#!/usr/bin/env bash
aws s3api list-buckets --query "Buckets[].Name" --output text \
  | tr '\t' '\n' \
  | grep -E '^chess-move-validator-frontend' \
  | while read -r B; do
      echo ">>> Emptying $B"
      aws s3 rm "s3://$B" --recursive

      # delete all object versions
      aws s3api list-object-versions --bucket "$B" \
        --output json --query '{Objects: Versions[].{Key:Key,VersionId:VersionId}}' \
        | jq -c '. + {Quiet:true}' \
        | aws s3api delete-objects --bucket "$B" --delete file:///dev/stdin 2>/dev/null

      # delete all delete-markers
      aws s3api list-object-versions --bucket "$B" \
        --output json --query '{Objects: DeleteMarkers[].{Key:Key,VersionId:VersionId}}' \
        | jq -c '. + {Quiet:true}' \
        | aws s3api delete-objects --bucket "$B" --delete file:///dev/stdin 2>/dev/null

      echo ">>> Deleting $B"
      aws s3api delete-bucket --bucket "$B"
    done
