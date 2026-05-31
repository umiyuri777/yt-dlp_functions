FROM public.ecr.aws/lambda/python:3.12

# Amazon Linux 2023 SPAL provides the runtime package as ffmpeg-free.
RUN dnf install -y spal-release \
    && dnf install -y ffmpeg-free tar xz \
    && dnf clean all

COPY requirements.txt ${LAMBDA_TASK_ROOT}/
RUN pip install --no-cache-dir -r ${LAMBDA_TASK_ROOT}/requirements.txt

COPY handler.py ${LAMBDA_TASK_ROOT}/

CMD ["handler.lambda_handler"]
