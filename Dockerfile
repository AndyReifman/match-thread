FROM python:3
ADD . /
RUN pip install --trusted-host pypi.python.org -r /requirements.txt
WORKDIR /

CMD ["python","./mtb.py"]
