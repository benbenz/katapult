foo = []

a = Array{Int16}(undef,100000,100000,3)
b = Array{Int16}(undef,100000,100000,3)
c = Array{Int16}(undef,100000,100000,3)
d = Array{Int16}(undef,100000,100000,3)
e = Array{Int16}(undef,100000,100000,3)
f = Array{Int16}(undef,100000,100000,3)
g = Array{Int16}(undef,100000,100000,3)
h = Array{Int16}(undef,100000,100000,3)
i = Array{Int16}(undef,100000,100000,3)
j = Array{Int16}(undef,100000,100000,3)
k = Array{Int16}(undef,100000,100000,3)
l = Array{Int16}(undef,100000,100000,3)
m = Array{Int16}(undef,100000,100000,3)

file = open("output.dat", "w")
write(file, "Julia DONE")
close(file)