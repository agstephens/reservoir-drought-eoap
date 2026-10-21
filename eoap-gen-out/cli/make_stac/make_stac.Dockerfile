FROM python:3-slim


WORKDIR /app


RUN pip install click==8.1.8 pystac shapely

COPY make_stac.py app.py

CMD ["python"]