import numpy , time , sys

a = numpy.arange(15).reshape(3, 5)

# file = open("I_RAN.TXT", "w")
# file.write("that's right\n")
# file.write(str(a.shape))
# file.close()

print(a,flush=True)
c=1
while c<int(sys.argv[2]):
    time.sleep(2)
    print("sleep",c)
    c=c+1

f = open("output1.dat", "a")
f.write("THIS IS DATA1")
f.close()

f = open("output2.dat", "a")
f.write("THIS IS DATA2")
f.close()