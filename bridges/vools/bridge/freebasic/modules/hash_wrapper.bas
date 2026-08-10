#include "crt/string.bi"
#include "crt/stdint.bi"
#include "crt/stddef.bi"

Type MD5Context
    state(0 To 3) As ULong
    count(0 To 1) As ULong
    buffer(0 To 63) As UByte
End Type

Private Const MD5_S11 = 7
Private Const MD5_S12 = 12
Private Const MD5_S13 = 17
Private Const MD5_S14 = 22
Private Const MD5_S21 = 5
Private Const MD5_S22 = 9
Private Const MD5_S23 = 14
Private Const MD5_S24 = 20
Private Const MD5_S31 = 4
Private Const MD5_S32 = 11
Private Const MD5_S33 = 16
Private Const MD5_S34 = 23
Private Const MD5_S41 = 6
Private Const MD5_S42 = 10
Private Const MD5_S43 = 15
Private Const MD5_S44 = 21

Private Function md5_F(ByVal x As ULong, ByVal y As ULong, ByVal z As ULong) As ULong
    Return (x And y) Or ((Not x) And z)
End Function

Private Function md5_G(ByVal x As ULong, ByVal y As ULong, ByVal z As ULong) As ULong
    Return (x And z) Or (y And (Not z))
End Function

Private Function md5_H(ByVal x As ULong, ByVal y As ULong, ByVal z As ULong) As ULong
    Return x Xor y Xor z
End Function

Private Function md5_I_func(ByVal x As ULong, ByVal y As ULong, ByVal z As ULong) As ULong
    Return y Xor (x Or (Not z))
End Function

Private Function rotate_left(ByVal x As ULong, ByVal n As Integer) As ULong
    Return (x Shl n) Or (x Shr (32 - n))
End Function

Private Sub md5_FF(ByRef a As ULong, ByVal b As ULong, ByVal c As ULong, ByVal d As ULong, ByVal x As ULong, ByVal s As Integer, ByVal ac As ULong)
    a = a + md5_F(b, c, d) + x + ac
    a = rotate_left(a, s)
    a = a + b
End Sub

Private Sub md5_GG(ByRef a As ULong, ByVal b As ULong, ByVal c As ULong, ByVal d As ULong, ByVal x As ULong, ByVal s As Integer, ByVal ac As ULong)
    a = a + md5_G(b, c, d) + x + ac
    a = rotate_left(a, s)
    a = a + b
End Sub

Private Sub md5_HH(ByRef a As ULong, ByVal b As ULong, ByVal c As ULong, ByVal d As ULong, ByVal x As ULong, ByVal s As Integer, ByVal ac As ULong)
    a = a + md5_H(b, c, d) + x + ac
    a = rotate_left(a, s)
    a = a + b
End Sub

Private Sub md5_II(ByRef a As ULong, ByVal b As ULong, ByVal c As ULong, ByVal d As ULong, ByVal x As ULong, ByVal s As Integer, ByVal ac As ULong)
    a = a + md5_I_func(b, c, d) + x + ac
    a = rotate_left(a, s)
    a = a + b
End Sub

Private Sub md5_transform(ByVal state As ULong Ptr, ByVal block As UByte Ptr)
    Dim As ULong a = state[0]
    Dim As ULong b = state[1]
    Dim As ULong c = state[2]
    Dim As ULong d = state[3]
    Dim As ULong x(0 To 15)
    Dim As Integer idx
    
    For idx = 0 To 15
        x(idx) = CULng(block[idx * 4]) Or _
                 CULng(block[idx * 4 + 1]) Shl 8 Or _
                 CULng(block[idx * 4 + 2]) Shl 16 Or _
                 CULng(block[idx * 4 + 3]) Shl 24
    Next
    
    md5_FF a, b, c, d, x(0), MD5_S11, CULng(&HD76AA478)
    md5_FF d, a, b, c, x(1), MD5_S12, CULng(&HE8C7B756)
    md5_FF c, d, a, b, x(2), MD5_S13, CULng(&H242070DB)
    md5_FF b, c, d, a, x(3), MD5_S14, CULng(&HC1BDCEEE)
    md5_FF a, b, c, d, x(4), MD5_S11, CULng(&HF57C0FAF)
    md5_FF d, a, b, c, x(5), MD5_S12, CULng(&H4787C62A)
    md5_FF c, d, a, b, x(6), MD5_S13, CULng(&HA8304613)
    md5_FF b, c, d, a, x(7), MD5_S14, CULng(&HFD469501)
    md5_FF a, b, c, d, x(8), MD5_S11, CULng(&H698098D8)
    md5_FF d, a, b, c, x(9), MD5_S12, CULng(&H8B44F7AF)
    md5_FF c, d, a, b, x(10), MD5_S13, CULng(&HFFFF5BB1)
    md5_FF b, c, d, a, x(11), MD5_S14, CULng(&H895CD7BE)
    md5_FF a, b, c, d, x(12), MD5_S11, CULng(&H6B901122)
    md5_FF d, a, b, c, x(13), MD5_S12, CULng(&HFD987193)
    md5_FF c, d, a, b, x(14), MD5_S13, CULng(&HA679438E)
    md5_FF b, c, d, a, x(15), MD5_S14, CULng(&H49B40821)
    
    md5_GG a, b, c, d, x(1), MD5_S21, CULng(&HF61E2562)
    md5_GG d, a, b, c, x(6), MD5_S22, CULng(&HC040B340)
    md5_GG c, d, a, b, x(11), MD5_S23, CULng(&H265E5A51)
    md5_GG b, c, d, a, x(0), MD5_S24, CULng(&HE9B6C7AA)
    md5_GG a, b, c, d, x(5), MD5_S21, CULng(&HD62F105D)
    md5_GG d, a, b, c, x(10), MD5_S22, CULng(&H2441453)
    md5_GG c, d, a, b, x(15), MD5_S23, CULng(&HD8A1E681)
    md5_GG b, c, d, a, x(4), MD5_S24, CULng(&HE7D3FBC8)
    md5_GG a, b, c, d, x(9), MD5_S21, CULng(&H21E1CDE6)
    md5_GG d, a, b, c, x(14), MD5_S22, CULng(&HC33707D6)
    md5_GG c, d, a, b, x(3), MD5_S23, CULng(&HF4D50D87)
    md5_GG b, c, d, a, x(8), MD5_S24, CULng(&H455A14ED)
    md5_GG a, b, c, d, x(13), MD5_S21, CULng(&HA9E3E905)
    md5_GG d, a, b, c, x(2), MD5_S22, CULng(&HFCEFA3F8)
    md5_GG c, d, a, b, x(7), MD5_S23, CULng(&H676F02D9)
    md5_GG b, c, d, a, x(12), MD5_S24, CULng(&H8D2A4C8A)
    
    md5_HH a, b, c, d, x(5), MD5_S31, CULng(&HFFFA3942)
    md5_HH d, a, b, c, x(8), MD5_S32, CULng(&H8771F681)
    md5_HH c, d, a, b, x(11), MD5_S33, CULng(&H6D9D6122)
    md5_HH b, c, d, a, x(14), MD5_S34, CULng(&HFDE5380C)
    md5_HH a, b, c, d, x(1), MD5_S31, CULng(&HA4BEEA44)
    md5_HH d, a, b, c, x(4), MD5_S32, CULng(&H4BDECFA9)
    md5_HH c, d, a, b, x(7), MD5_S33, CULng(&HF6BB4B60)
    md5_HH b, c, d, a, x(10), MD5_S34, CULng(&HBEBFBC70)
    md5_HH a, b, c, d, x(13), MD5_S31, CULng(&H289B7EC6)
    md5_HH d, a, b, c, x(0), MD5_S32, CULng(&HEAA127FA)
    md5_HH c, d, a, b, x(3), MD5_S33, CULng(&HD4EF3085)
    md5_HH b, c, d, a, x(6), MD5_S34, CULng(&H4881D05)
    md5_HH a, b, c, d, x(9), MD5_S31, CULng(&HD9D4D039)
    md5_HH d, a, b, c, x(12), MD5_S32, CULng(&HE6DB99E5)
    md5_HH c, d, a, b, x(15), MD5_S33, CULng(&H1FA27CF8)
    md5_HH b, c, d, a, x(2), MD5_S34, CULng(&HC4AC5665)
    
    md5_II a, b, c, d, x(0), MD5_S41, CULng(&HF4292244)
    md5_II d, a, b, c, x(7), MD5_S42, CULng(&H432AFF97)
    md5_II c, d, a, b, x(14), MD5_S43, CULng(&HAB9423A7)
    md5_II b, c, d, a, x(5), MD5_S44, CULng(&HFC93A039)
    md5_II a, b, c, d, x(12), MD5_S41, CULng(&H655B59C3)
    md5_II d, a, b, c, x(3), MD5_S42, CULng(&H8F0CCC92)
    md5_II c, d, a, b, x(10), MD5_S43, CULng(&HFFEFF47D)
    md5_II b, c, d, a, x(1), MD5_S44, CULng(&H85845DD1)
    md5_II a, b, c, d, x(8), MD5_S41, CULng(&H6FA87E4F)
    md5_II d, a, b, c, x(15), MD5_S42, CULng(&HFE2CE6E0)
    md5_II c, d, a, b, x(6), MD5_S43, CULng(&HA3014314)
    md5_II b, c, d, a, x(13), MD5_S44, CULng(&H4E0811A1)
    md5_II a, b, c, d, x(4), MD5_S41, CULng(&HF7537E82)
    md5_II d, a, b, c, x(11), MD5_S42, CULng(&HBD3AF235)
    md5_II c, d, a, b, x(2), MD5_S43, CULng(&H2AD7D2BB)
    md5_II b, c, d, a, x(9), MD5_S44, CULng(&HEB86D391)
    
    state[0] += a
    state[1] += b
    state[2] += c
    state[3] += d
End Sub

Private Sub md5_init(ByVal ctx As MD5Context Ptr)
    ctx->state(0) = CULng(&H67452301)
    ctx->state(1) = CULng(&HEFCDAB89)
    ctx->state(2) = CULng(&H98BADCFE)
    ctx->state(3) = CULng(&H10325476)
    ctx->count(0) = 0
    ctx->count(1) = 0
End Sub

Private Sub md5_update(ByVal ctx As MD5Context Ptr, ByVal in_data As UByte Ptr, ByVal in_len As ULong)
    Dim As ULong i, idx, partLen
    
    idx = CULng(ctx->count(0) Shr 3) And CULng(&H3F)
    ctx->count(0) += in_len Shl 3
    
    If ctx->count(0) < (in_len Shl 3) Then
        ctx->count(1) += 1
    End If
    ctx->count(1) += in_len Shr 29
    
    partLen = 64 - idx
    
    If in_len >= partLen Then
        memcpy(@ctx->buffer(idx), in_data, partLen)
        md5_transform @ctx->state(0), @ctx->buffer(0)
        
        i = partLen
        While i + 63 < in_len
            md5_transform @ctx->state(0), @in_data[i]
            i += 64
        Wend
        
        idx = 0
    Else
        i = 0
    End If
    
    memcpy(@ctx->buffer(idx), @in_data[i], in_len - i)
End Sub

Private Sub md5_final(ByVal digest As UByte Ptr, ByVal ctx As MD5Context Ptr)
    Dim As UByte bits(7)
    Dim As ULong idx, pad_len, i
    Dim As Integer k
    Dim As UByte padding(127)
    
    For k = 0 To 7
        bits(k) = CUByte((ctx->count(k \ 4) Shr ((k And 3) * 8)))
    Next
    
    idx = CULng(ctx->count(0) Shr 3) And 63
    
    padding(0) = &H80
    
    If idx < 56 Then
        pad_len = 56 - idx
    Else
        pad_len = 120 - idx
    End If
    
    For i = 1 To pad_len - 1
        padding(i) = 0
    Next
    
    md5_update ctx, @padding(0), pad_len
    md5_update ctx, @bits(0), 8
    
    For k = 0 To 3
        digest[k * 4] = CUByte(ctx->state(k))
        digest[k * 4 + 1] = CUByte(ctx->state(k) Shr 8)
        digest[k * 4 + 2] = CUByte(ctx->state(k) Shr 16)
        digest[k * 4 + 3] = CUByte(ctx->state(k) Shr 24)
    Next
End Sub

Private Function to_hex_char(ByVal v As UByte) As UByte
    If v <= 9 Then
        Return Asc("0") + v
    Else
        Return Asc("a") + v - 10
    End If
End Function

Function fb_hash_md5(ByVal input_str As ZString Ptr, ByVal out_buf As ZString Ptr, ByVal out_size As Long) As Long Export
    Dim As MD5Context ctx
    Dim As UByte digest(15)
    Dim As Integer k
    
    md5_init @ctx
    md5_update @ctx, Cast(UByte Ptr, input_str), Len(*input_str)
    md5_final @digest(0), @ctx
    
    For k = 0 To 15
        out_buf[k * 2] = to_hex_char(digest(k) Shr 4)
        out_buf[k * 2 + 1] = to_hex_char(digest(k) And &HF)
    Next
    
    out_buf[32] = 0
    Return 0
End Function
