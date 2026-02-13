ARG BUILD_FROM
FROM ${BUILD_FROM}

RUN apk add --no-cache python3 py3-pip
RUN pip3 install --no-cache-dir paho-mqtt

WORKDIR /app
COPY app.py /app/app.py
COPY run.sh /run.sh
RUN chmod a+x /run.sh

CMD [ "/run.sh" ]
