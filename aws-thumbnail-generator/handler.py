from datetime import datetime
import boto3
from io import BytesIO
from PIL import Image, ImageOps
import os
import uuid
import json

# Using AWS boto3 client

s3 = boto3.client('s3')
dynamodb = boto3.resource('dynamodb', region_name=str(os.environ['REGION_NAME']))

size = int(os.getenv("THUMBNAIL_SIZE"))
dbtable = str(os.getenv('DYNAMODB_TABLE'))
# Generating thumbnail images from S3 bucket as they are added
def s3_thumbnail_generator(event, context):
    # parse event
    print("Event:::", event)

    bucket = event['Records'][0]['s3']['bucket']['name']
    key = event['Records'][0]['s3']['object']['key']
    img_size = event['Records'][0]['s3']['object']['size']

    # creating thumbnail and adding it to bucket
    if (not key.endswith('_thumbnail.png')):

        image = get_s3_image(bucket, key)
        thumbnail = image_to_thumbnail(image)
        
        thumbnail_key = new_filename(key)

        url = upload_to_s3(bucket, thumbnail_key, thumbnail, img_size)

        # Saving url to dynamodb
        s3_save_url_to_dynamodb(url_path=url, img_size=img_size)
        return url

def get_s3_image(bucket, key):
    response = s3.get_object(Bucket=bucket, Key=key)
    imagecontent = response['Body'].read()
    
    image_file = BytesIO(imagecontent)
    return Image.open(image_file)


def image_to_thumbnail(image):
    return ImageOps.fit(image, (size, size), Image.ANTIALIAS)

def new_filename(key):
    key_split = key.rsplit('.',1)
    return key_split[0] + "_thumbnail.png"

def upload_to_s3(bucket, key, image, img_size):
    # Save img to BytesIO object
    out_thumbnail = BytesIO()

    image.save(out_thumbnail, 'PNG')
    out_thumbnail.seek(0)
    
    response = s3.put_object(
        ACL='public-read',
        Body=out_thumbnail,
        Bucket=bucket,
        ContentType='image/png',
        Key=key
    )
    print(response)

    url = '{}/{}/{}'.format(s3.meta.endpoint_url, bucket, key)
    return url

def s3_save_url_to_dynamodb(url_path, img_size):
    # Dividing by thousand reduce the dimensions
    sizeToInt = float(img_size*0.53)/1000
    table = dynamodb.Table(dbtable)
    
    # creating fields
    response = table.put_item(
        Item={
            'id': str(uuid.uuid4()),
            'url': str(url_path),
            'approxReducedSize': str(sizeToInt) + str('KB'),
            'createdAt': str(datetime.now()),
            'updatedAt': str(datetime.now())
        }
    )

    return {
        'statusCode': 200,
        'message':'success',
        "data": {'test'},
        'headers': {'Content-Type': 'application/json'},
        'body': json.dumps(response)
    }

def s3_get_thumbnail_urls(event, context):
    table = dynamodb.Table(dbtable)
    response = table.scan()
    data = response['Items']
    
    # Paginate through results in a loop 
    while 'LastEvaluatedKey' in response:
        response = table.scan(ExclusiveStartKey=response['LastEvaluatedKey'])
        data.extend(response['Items'])
    return {
        'statusCode': 200,
        'headers': {'Content-Type': 'application/json'},
        'body': json.dumps(data),
    }


def s3_get_item(event, context):
    table = dynamodb.Table(dbtable)
    response = table.get_item(
        Key={
            'id': event['pathParameters']['id']
        } 
    )
    item = response['Item']
    return {
        'statusCode': 200,
        'headers': {'ContentType': 'application/json', 'Access-Control-Allow-Origin': '*'},
        'body': json.dumps(item),
        'isBase64Encoded': False,
    }

def s3_delete_item(event, context):
    table = dynamodb.Table(dbtable)
    item_id = event['pathParameters']['id']
    
    response = {
        'statusCode': 500,
        'body': f"Error occured while deleting post {item_id}"
    }
    
    delete_response = table.delete_item(Key={
        'id': item_id
    }) 
    
    all_good_response = {
        "deleted": True,
        "itemDeletedId": item_id
    }
    
    if delete_response['ResponseMetadata']['HTTPStatusCode'] == 200:
        response = {
            'statusCode': 200,
           'headers': {'ContentType': 'application/json', 'Access-Control-Allow-Origin': '*'},
            'body': json.dumps(all_good_response)
        }
    return response