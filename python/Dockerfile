FROM python:3.8

# For a smaller container use the following instead
#FROM python:3.8-slim
	
WORKDIR /usr/src/app
		
COPY requirements.txt ./
		
RUN pip install --no-cache-dir -r requirements.txt
		
COPY . .
		
CMD [ "python", "./sppmon.py" ]
