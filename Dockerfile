FROM python:3.13.7-alpine3.22

WORKDIR /app

# Define so the script knows not to download a new driver version, as
# this Docker image already downloads a compatible chromedriver
ENV AUTO_SOUTHWEST_CHECK_IN_DOCKER=1

RUN apk add --update --no-cache chromium chromium-chromedriver xvfb xauth

RUN adduser -D auto-southwest-check-in -h /app
RUN chown -R auto-southwest-check-in:auto-southwest-check-in /app
USER auto-southwest-check-in

COPY requirements.txt ./
RUN pip3 install --upgrade pip && pip3 install --no-cache-dir -r requirements.txt && rm -r /app/.cache

COPY . .

# Default to the United check-in workflow so running the container with two
# arguments (confirmation number and last name) performs a United check-in.
# Southwest users can still override the entrypoint at runtime, e.g.:
#   docker run -d --entrypoint python3 kylewhirl/auto-united-check-in southwest.py ABC123 FIRST LAST
ENTRYPOINT ["python3", "-u", "united.py"]
