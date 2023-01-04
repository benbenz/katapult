foo = []

a = Array{Int8}(undef,10000,10000,3)
b = Array{Int8}(undef,10000,10000,3)
c = Array{Int8}(undef,10000,10000,3)
d = Array{Int8}(undef,10000,10000,3)
e = Array{Int8}(undef,10000,10000,3)
f = Array{Int8}(undef,10000,10000,3)
g = Array{Int8}(undef,10000,10000,3)
h = Array{Int8}(undef,10000,10000,3)
i = Array{Int8}(undef,10000,10000,3)
j = Array{Int8}(undef,10000,10000,3)
k = Array{Int8}(undef,10000,10000,3)
l = Array{Int8}(undef,10000,10000,3)
m = Array{Int8}(undef,10000,10000,3)

file = open("output.dat", "w")
write(file, "Julia DONE")
close(file)