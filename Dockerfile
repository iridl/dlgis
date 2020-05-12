FROM centos:centos8
MAINTAINER IRI, Columbia University <help@iri.columbia.edu>

RUN yum -y update && \
    yum -y install curl bzip2 && \
    curl -sSL https://repo.continuum.io/miniconda/Miniconda3-latest-Linux-x86_64.sh -o /tmp/miniconda.sh && \
    bash /tmp/miniconda.sh -bfp /usr/local && \
    conda config --set auto_update_conda False && \
    conda update -n base -c defaults conda && \
    conda install -y 'python==3.8.*' 'gdal=3.0.*' && \
    conda --version && \
    python --version

RUN pip install black mypy flake8 pylint
