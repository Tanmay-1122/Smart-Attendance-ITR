import os
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'
from app import create_app
app = create_app()
if __name__ == '__main__':
    # Set a fixed secret key for dev (don't use this in production)
    app.config['SECRET_KEY'] = 'dev-secret-key-change-in-prod'
    app.run(debug=True, host='0.0.0.0', port=5000)
