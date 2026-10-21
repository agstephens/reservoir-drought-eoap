FROM python:3-slim


WORKDIR /app


RUN pip install click==8.1.8 numpy pyproj rasterio scipy shapely

COPY extract_water.py app.py

CMD ["python"]