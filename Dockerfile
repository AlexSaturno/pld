FROM python:3.11

WORKDIR /work
COPY . .

RUN pip3 install -r requirements.txt

EXPOSE 8501

CMD ["/usr/local/bin/streamlit", "run", "/work/extracao_noticias.py"]
