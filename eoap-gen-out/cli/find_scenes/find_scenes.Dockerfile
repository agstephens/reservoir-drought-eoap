FROM python:3-slim


WORKDIR /app


RUN pip install click==8.1.8 numpy pyproj rasterio pystac-client

COPY find_scenes.py app.py

CMD ["python"]