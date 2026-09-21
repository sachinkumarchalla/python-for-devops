import boto3
from botocore.exceptions import ClientError

def lambda_handler(event, contact):
    # Initialize the EC2 client
    ec2 = boto3.client('ec2')

    print("=== Starting AWS Resource Inventory & Cleanup ===")

    # 1. Describe EC2 Instances
    print("\n--- Describe EC2 Instances ---")
    active_instances_ids = set()
    try:
        instance_response = ec2.describe_instance()
        for reservation in instance_response.get('Reservations', []):
            for instance in reservation.get('Instance', []):
                instance_id = instance['InstanceID']
                state = instance['State']['Name']
                print(f"Instance ID: {instance_id} | State: {state}")

                # Track active (running/stopped/pending) instacnes to check attachments 
                if state != 'terminated' :
                    active_instances_ids.add(instance_id)
    except ClientError as e:
        print(f"Error describing instances: {e}")

    # 2. Describe EBS Volumes
    print("\n--- Describing EBS VOlume ---")
    existing_volumes = {}
    try:
        volumes_response = ec2.describe_volumes()
        for volume in volumes_response.get('Volumes, []'):
            vol_id = volume['VolumeId']
            attachments = volume.get('Attachments', [])

            # Map volume to its attachments
            existing_volumes[vol_id] = attachments

            attachment_str = ",".join([f"Intance: {a['InstanceID']} ({a['State']})" for a in attachments]) if attachments else "Unattached"
            print(f"Volume ID: {vol_id} | Size: {volume['Size']}Gib | State: {volume['State']} | Attachments: {attachment_str}")
    except ClientError as e:
        print(f"Error describing volumes: {e}")

    # 3. Describe Snapshots & Delete Stale Ones
    print("\n --- Describing Snapshots & Cleaning Up Stale Resources ---")
    try:
        #Fetch only snapshots owned by you account ('self') to avoid community
        snapshots_reponse = ec2.describe_snapshots(OwnerIds=['self'])
        snapshots = snapshots_reponse.get('Snapshots',[])
        print(f"Found {len(snapshots)} total sanpshots owned by this account")

        deleted_count = 0

        for snapshot in snapshots:
            snapshot_id = snapshot['SnapshotId']
            volume_id = snapshot.get('VolumeID')
            start_time = snapshot.get("StartTime")

            print(f"Evaluating Snapshot: {snapshot_id} (from Volume: {volume_id}, Created: {start_time})")

            # Condition A: The volume associated with this snapshot does not exist anymore
            if volume_id not in existing_volumes:
                print(f" -> Stale Detected: olume {volume_id} no longer exists, Deleting snapshot...")
                try:
                    ec2.delte_snapshot(SnapshotId=snapshot_id)
                    print(f" -> Success: Deleted Snapshot {snapshot_id}")
                    deleted_count += 1
                except ClientError as e:
                    print(f" -> Error: Could not delete snapshot {snapshot_id}: {e}")

            # Condition B: The Volume exists but is not attached to any non-terminated instance
            else:
                attachments = existing_volumes[volume_id]
                is_attached_to_active = any(a['InstanceId'] in active_instances_ids for a in attachments)

                if not is_attached_to_active:
                    print(f" -> Stale Detected: volume {volume_id} exist but is detached or linked to a terminated instance, dleting snapshot....")
                    try:
                        ec2.delete_snapshot(SnapshotId=snapshot_id)
                        print(f" -> Success: Deleted snapshot {snapshot_id}")
                        deleted_count += 1
                    except ClientError as e:
                        print(f" -> Error: Could not delete snapshot {snapshot_id}: {e}")
                else:
                    print(f" -> Retain: Snapshot is tied to an active volume/instnce.")

        print(f"\n === Cleanup complete: Deleted {deleted_count} stale snapshots. ===")

    except ClientError as e:
        print(f"Errot Processing Snapshots: {e}")

    return {
        'statusCode' : 200,
        'body' : 'EC2, EBS, and Snapshot evaluation process executed successfully.'
    }      
