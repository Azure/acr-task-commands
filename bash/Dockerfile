FROM mcr.microsoft.com/azurelinux/base/core:3.0
LABEL maintainer=acr-feedback@microsoft.com

COPY docker-entrypoint.sh /usr/local/bin/
ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["bash"]