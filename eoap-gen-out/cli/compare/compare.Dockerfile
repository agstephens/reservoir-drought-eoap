FROM python:3-slim


WORKDIR /app


RUN pip install click==8.1.8 matplotlib numpy pyproj shapely

COPY compare.py app.py

CMD ["python"]