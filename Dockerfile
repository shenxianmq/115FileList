# 使用官方 Python 镜像作为基础镜像
FROM shenxianmq/115_file_list_env:latest

# 设置环境变量
ENV LANG="C.UTF-8" \
    TZ="Asia/Shanghai" \
    PUID=0 \
    PGID=0 \
    UMASK=000

ARG UID=1000
ARG GID=1000

# 创建用户组和用户
RUN addgroup --gid $GID user && \
    adduser --uid $UID --gid $GID --disabled-password --gecos "" user

# # 创建一个非root用户，指定用户和组 ID
# RUN groupadd -r -g $GROUP_ID autoSymlink && useradd -r -g autoSymlink -u $USER_ID autoSymlink


# 从当前目录复制所有文件到工作目录
# COPY --chown=user:user . /app

COPY . /app

# 设置工作目录
WORKDIR /app

RUN chmod -R 777 /app

# 在构建过程中为脚本赋予执行权限
RUN chmod +x /app/start.sh

# USER user

# 定义容器启动命令
ENTRYPOINT ["/app/start.sh"]