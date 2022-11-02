import numpy

a = numpy.arange(15).reshape(3, 5)

file = open("I_RAN.TXT", "w")
file.write("that's right\n")
file.write(str(a.shape))
file.close()

print(a)