python3 review_pdfs.py -vv \
  --input-dir /data \
  --output /db/ai_review.xlsx \
  --openai-base-url http://10.6.6.20:11434 \
  --openai-model qwen3.5:9b \
  --llm-prompt-file llm_prompt.txt \
  --txt-output-dir /data/txt
