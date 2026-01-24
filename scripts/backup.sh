#!/bin/bash
# Daily database backup script
# Overwrites previous backup to save disk space

BACKUP_FILE="/backups/database.sql"

pg_dump -U postgres -d taxi_parser > "$BACKUP_FILE"

if [ $? -eq 0 ]; then
    echo "$(date '+%Y-%m-%d %H:%M:%S') - Backup completed successfully"
else
    echo "$(date '+%Y-%m-%d %H:%M:%S') - Backup failed" >&2
    exit 1
fi
