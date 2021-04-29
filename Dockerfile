# An Ubuntu 20.04 that is ready to run Jupyter
FROM jupyter/base-notebook:584f43f06586

# Downgrade Python to 3.6 - the outdated cwb-python dependency needs it.
# The install all the system dependencies using conda for consistency.
RUN conda install python=3.6 && \
    conda install -c conda-forge \
        bison \
        bottleneck \
        cython \
        flex \
        gcc_linux-64 \
        git \
        gxx_linux-64 \
        glib \
        make \
        ncurses \
        pcre \
        perl \
        pkg-config \
        readline && \
    conda clean -a -q -y

# Download the source code of Corpus Workbench
RUN wget https://downloads.sourceforge.net/project/cwb/cwb/cwb-3.4-beta/cwb-3.4.22-source.tar.gz && \
    tar xzvf cwb-3.4.22-source.tar.gz && \
    rm cwb-3.4.22-source.tar.gz

# Compile and install - Corpus Workbench does not seem to fully honour environment variables
# so we need to tweak the platform configuration a bit
RUN cd cwb-3.4.22 && \
    sed -i 's|CC = gcc|CC = /opt/conda/bin/x86_64-conda-linux-gnu-cc|g' ./config/platform/unix && \
    sed -i 's|DEPEND = gcc|DEPEND = /opt/conda/bin/x86_64-conda-linux-gnu-cc|g' ./config/platform/unix && \
    sed -i 's|AR = ar|AR = /opt/conda/bin/x86_64-conda-linux-gnu-ar|g' ./config/platform/unix && \
    sed -i 's|RANLIB = ranlib|RANLIB = /opt/conda/bin/x86_64-conda-linux-gnu-ranlib|g' ./config/platform/unix && \
    make all PLATFORM=linux && \
    make install PLATFORM=linux PREFIX=/opt/conda

# Install the Python API
RUN CWB_DIR=/opt/conda conda run -n base --no-capture-output python -m pip install cwb-ccc
