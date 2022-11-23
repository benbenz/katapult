wget https://julialang-s3.julialang.org/bin/linux/x64/1.8/julia-1.8.0-linux-x86_64.tar.gz
tar -xvzf julia-1.8.0-linux-x86_64.tar.gz
sudo cp -r julia-1.8.0 /opt/
sudo ln -s /opt/julia-1.8.0/bin/julia /usr/local/bin/julia
rm -rf julia-1.8.0-linux-x86_64
rm -rf julia-1.8.0
rm -f julia-1.8.0-linux-x86_64.tar.gz