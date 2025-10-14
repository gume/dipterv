FROM mcr.microsoft.com/playwright:v1.56.0-noble

# Install Python and dependencies
RUN \
 rm -rf /var/lib/apt/lists/* && \
 apt-get clean && \
 apt-get update

RUN apt-get install -y python3 python3-pip python3-venv

# Create virtual environment
RUN python3 -m venv /venv
ENV PATH="/venv/bin:$PATH"

# Install Playwright inside the virtual environment
RUN pip install --upgrade pip && \
    pip install playwright openpyxl pandas && \
    playwright install

# Copy your script
#COPY your_script.py /app/your_script.py
WORKDIR /app

#CMD ["python3", "your_script.py"]
CMD ["tail", "-f", "/dev/null"]
