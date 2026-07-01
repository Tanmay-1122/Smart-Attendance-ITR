import ssl
from app import create_app
app = create_app()
if __name__=='__main__':
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain('cert.pem', 'key.pem')
    app.run(debug=False, host='0.0.0.0', port=5000, ssl_context=ctx)
