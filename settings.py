import os

DEBUG = os.getenv('DEBUG') in ['True', 'true', '1', 'yes']
SECRET_KEY = os.getenv('SECRET_KEY') or 'asdbaskdb'

GITHUB_APP_ID = os.getenv('GITHUB_APP_ID')
GITHUB_APP_SECRET = os.getenv('GITHUB_APP_SECRET')
GITHUB_APP_STATE = os.getenv('GITHUB_APP_STATE') or 'banana'

REDIS_URL = os.getenv('REDISCLOUD_URL')
