# 墨督督学习空间 · 微信云托管版后端
# 构建上下文 = 本目录（mdd-cloudrun/），微信云托管控制台上传整个目录的 zip 即可
FROM python:3.11-slim

WORKDIR /srv

COPY backend/web/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# 目录布局必须与服务器一致：ROOT=/srv/mdd-knowledge，APP=ROOT/apps/knowledge-agent，
# ROOT/designs 下放种子数据（bootstrap 用 APP.parents[1] 定位）
COPY backend/web /srv/mdd-knowledge/apps/knowledge-agent/web
COPY backend/intake /srv/mdd-knowledge/apps/knowledge-agent/intake
COPY designs/knowledge-agent-intake /srv/mdd-knowledge/designs/knowledge-agent-intake

# 云托管固定配置：
#  CLOUD=1        放开「仅允许本机访问」的 Host 限定（流量走微信内部通道）
#  WORKER=0       关闭容器内生成任务 worker——生成/解析只在阿里云主实例跑，避免多实例抢任务
#  密钥不入镜像：DATABASE_URL / DEEPSEEK_API_KEY / master.key 内容在云托管控制台环境变量与文件里配置
ENV KNOWLEDGE_STORAGE_DIR=/srv/mdd-knowledge/apps/knowledge-agent/runtime/materials \
    KNOWLEDGE_MASTER_KEY_FILE=/srv/mdd-knowledge/apps/knowledge-agent/runtime/master.key \
    KNOWLEDGE_CLOUD=1 \
    KNOWLEDGE_WORKER=0 \
    KNOWLEDGE_PORT=80

WORKDIR /srv/mdd-knowledge/apps/knowledge-agent/web
EXPOSE 80
CMD ["python","-B","-m","uvicorn","app:app","--host","0.0.0.0","--port","80","--proxy-headers","--forwarded-allow-ips=*"]
