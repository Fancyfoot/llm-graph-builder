import os
import logging
from google.cloud import storage
from langchain_community.document_loaders import GCSFileLoader, GCSDirectoryLoader
from langchain_community.document_loaders import PyMuPDFLoader
from langchain_core.documents import Document
from PyPDF2 import PdfReader
import io
from google.oauth2.credentials import Credentials
import time

def get_gcs_bucket_files_info(gcs_project_id, gcs_bucket_name, gcs_bucket_folder, creds):
    storage_client = storage.Client(project=gcs_project_id, credentials=creds)
    file_name=''
    try:
      bucket = storage_client.bucket(gcs_bucket_name.strip())
      buckets_list = [bkt.name for bkt in storage_client.list_buckets()]
      if bucket.name in buckets_list:
        blobs = storage_client.list_blobs(gcs_bucket_name.strip(), prefix=gcs_bucket_folder if gcs_bucket_folder else '')
        lst_file_metadata=[]
        for blob in blobs:
          if blob.content_type == 'application/pdf':
            folder_name, file_name = os.path.split(blob.name)
            file_size = blob.size
            source_url= blob.media_link
            gcs_bucket = gcs_bucket_name
            lst_file_metadata.append({'fileName':file_name,'fileSize':file_size,'url':source_url, 
                                      'gcsBucket': gcs_bucket, 'gcsBucketFolder':folder_name if folder_name else '',
                                      'gcsProjectId': gcs_project_id}) 
        return lst_file_metadata
      else:
        file_name=''
        message=f" Bucket:{gcs_bucket_name} does not exist in Project:{gcs_project_id}. Please provide valid GCS bucket name"
        logging.info(f"Bucket : {gcs_bucket_name} does not exist in project : {gcs_project_id}")
        raise Exception(message)
    except Exception as e:
      error_message = str(e)
      logging.error(f"Unable to create source node for gcs bucket file {file_name}")
      logging.exception(f'Exception Stack trace: {error_message}')
      raise Exception(error_message)

def load_pdf(file_path):
    return PyMuPDFLoader(file_path)

def get_documents_from_gcs(gcs_project_id, gcs_bucket_name, gcs_bucket_folder, gcs_blob_filename, access_token=None):

  if gcs_bucket_folder is not None:
    if gcs_bucket_folder.endswith('/'):
      blob_name = gcs_bucket_folder+gcs_blob_filename
    else:
      blob_name = gcs_bucket_folder+'/'+gcs_blob_filename 
  else:
      blob_name = gcs_blob_filename  
  #credentials, project_id = google.auth.default()
  logging.info(f"GCS project_id : {gcs_project_id}")  
  #loader = GCSFileLoader(project_name=gcs_project_id, bucket=gcs_bucket_name, blob=blob_name, loader_func=load_pdf)
  # pages = loader.load()
  # file_name = gcs_blob_filename
  #creds= Credentials(access_token)
  if access_token is None:
    storage_client = storage.Client(project=gcs_project_id)
  else:
    creds= Credentials(access_token)
    storage_client = storage.Client(project=gcs_project_id, credentials=creds)
  print(f'BLOB Name: {blob_name}')
  bucket = storage_client.bucket(gcs_bucket_name)
  blob = bucket.blob(blob_name) 
  content = blob.download_as_bytes()
  pdf_file = io.BytesIO(content)
  pdf_reader = PdfReader(pdf_file)

    # Extract text from all pages
  text = ""
  for page in pdf_reader.pages:
        text += page.extract_text()
  pages = [Document(page_content = text)]
  return gcs_blob_filename, pages

def upload_file_to_gcs(file_chunk, chunk_number, original_file_name, bucket_name):
  storage_client = storage.Client()
  
  file_name = f'{original_file_name}_part_{chunk_number}'
  bucket = storage_client.bucket(bucket_name)
  file_data = file_chunk.file.read()
  # print(f'data after read {file_data}')
       
  blob = bucket.blob(file_name)
  file_io = io.BytesIO(file_data)
  blob.upload_from_file(file_io)
  # Define the lifecycle rule to delete objects after 6 hours
  # rule = {
  #     "action": {"type": "Delete"},
  #     "condition": {"age": 1}  # Age in days (24 hours = 1 days)
  # }

  # # Get the current lifecycle policy
  # lifecycle = list(bucket.lifecycle_rules)

  # # Add the new rule
  # lifecycle.append(rule)

  # # Set the lifecycle policy on the bucket
  # bucket.lifecycle_rules = lifecycle
  # bucket.patch()
  time.sleep(1)
  logging.info('Chunk uploaded successfully in gcs')
  
def merge_file_gcs(bucket_name, original_file_name: str):
    storage_client = storage.Client()
    # Retrieve chunks from GCS
    blobs = storage_client.list_blobs(bucket_name, prefix=f"{original_file_name}_part_")
    chunks = []
    for blob in blobs:
      chunks.append(blob.download_as_bytes())
      blob.delete()

    # Merge chunks into a single file
    merged_file = b"".join(chunks)
    blob = storage_client.bucket(bucket_name).blob(original_file_name)
    logging.info('save the merged file from chunks in gcs')
    file_io = io.BytesIO(merged_file)
    blob.upload_from_file(file_io)
    pdf_reader = PdfReader(file_io)
    file_size = len(merged_file)
    total_pages = len(pdf_reader.pages)
    
    return total_pages, file_size
  
def delete_file_from_gcs(bucket_name, file_name):
  try:
    storage_client = storage.Client()
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(file_name)
    if blob.exists():
      blob.delete()
    logging.info('File deleted from GCS successfully')
  except:
    raise Exception('BLOB not exists in GCS')