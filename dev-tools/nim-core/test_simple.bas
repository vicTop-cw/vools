#include "crt/string.bi"
#include "crt/stdint.bi"
#include "crt/stddef.bi"

Private Function md5_F(ByVal x As UInteger, ByVal y As UInteger, ByVal z As UInteger) As UInteger
    Return (x And y) Or ((Not x) And z)
End Function

Private Function rotate_left(ByVal x As UInteger, ByVal n As Integer) As UInteger
    Return (x Shl n) Or (x Shr (32 - n))
End Function

Private Sub md5_FF(ByRef a As UInteger, ByVal b As UInteger, ByVal c As UInteger, ByVal d As UInteger, ByVal x As UInteger, ByVal s As Integer, ByVal ac As UInteger)
    a = a + md5_F(b, c, d) + x + ac
    a = rotate_left(a, s)
    a = a + b
End Sub

Private Sub md5_transform(ByVal state As UInteger Ptr, ByVal block As UByte Ptr)
    Dim As UInteger a = state[0]
    Dim As UInteger b = state[1]
    Dim As UInteger c = state[2]
    Dim As UInteger d = state[3]
    Dim As UInteger x(0 To 15)
    Dim As Integer i
    Dim As UInteger ac_val
    
    For i = 0 To 15
        x(i) = CUInt(block[i * 4])
    Next
    
    ac_val = &HD76AA478
    md5_FF a, b, c, d, x(0), 7, ac_val
End Sub

Function fb_hash_md5(ByVal input_str As ZString Ptr, ByVal out_buf As ZString Ptr, ByVal out_size As Long) As Long Export
    Return 0
End Function
