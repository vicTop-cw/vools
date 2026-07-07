'坏坏小生 QQ 20273541  2023/04/07  按WINDOWS9的方式重写
#Define SHA256H0 &H6A09E667
#Define SHA256H1 &HBB67AE85
#Define SHA256H2 &H3C6EF372
#Define SHA256H3 &HA54FF53A
#Define SHA256H4 &H510E527F
#Define SHA256H5 &H9B05688C
#Define SHA256H6 &H1F83D9AB
#Define SHA256H7 &H5BE0CD19
#define SHA256_ROTL(x ,n)(((x) Shl (n)) or ((x) Shr (32 - (n))))
#define SHA256_ROTR(x ,n)(((x) Shr (n)) or ((x) Shl (32 - (n))))
#define SHA256_Ch(x ,y ,z)((z) Xor ((x) and ((y) Xor (z))))
#define SHA256_Maj(x ,y ,z)(((x) And ((y) or (z))) or ((y) And (z)))
#define SHA256_E0(x)(SHA256_ROTR((x) ,2) Xor SHA256_ROTR((x) ,13) Xor SHA256_ROTR((x) ,22))
#define SHA256_E1(x)(SHA256_ROTR((x) ,6) Xor SHA256_ROTR((x) ,11) Xor SHA256_ROTR((x) ,25))
#define SHA256_00(x)(SHA256_ROTR((x) ,7) xor SHA256_ROTR((x) ,18) xor ((x) Shr 3))
#define SHA256_01(x)(SHA256_ROTR((x) ,17) xor SHA256_ROTR((x) ,19) xor ((x) Shr 10))

Type SHA256Checksum
Public : 
   Declare Constructor()
   Declare Destructor()
   Declare Sub Transform(byval inpt As UByte Ptr)
   Declare Sub Update(byval dat As UByte Ptr ,byval length As ULongInt)
   Declare Function Final() As String
Private : 
   As ULongInt state(8)
   As ULongInt count(2)
   As UByte buf(64)
End Type
Constructor SHA256Checksum
   state(0) = SHA256H0
   state(1) = SHA256H1
   state(2) = SHA256H2
   state(3) = SHA256H3
   state(4) = SHA256H4
   state(5) = SHA256H5
   state(6) = SHA256H6
   state(7) = SHA256H7
End Constructor
Destructor SHA256Checksum
  
End Destructor
Sub SHA256Checksum.Transform(byval inpt As UByte Ptr)
   Dim As UInteger a ,b ,c ,d ,e ,f ,g ,h ,T1,T2
   Dim As UInteger w(64)
   
   Dim As Integer i
      dim K(64) as long = {_
      &H428A2F98 ,&H71374491 ,&HB5C0FBCF ,&HE9B5DBA5 ,&H3956C25B ,&H59F111F1 ,&H923F82A4 ,&HAB1C5ED5 , _
      &HD807AA98 ,&H12835B01 ,&H243185BE ,&H550C7DC3 ,&H72BE5D74 ,&H80DEB1FE ,&H9BDC06A7 ,&HC19BF174 , _
      &HE49B69C1 ,&HEFBE4786 ,&H0FC19DC6 ,&H240CA1CC ,&H2DE92C6F ,&H4A7484AA ,&H5CB0A9DC ,&H76F988DA , _
      &H983E5152 ,&HA831C66D ,&HB00327C8 ,&HBF597FC7 ,&HC6E00BF3 ,&HD5A79147 ,&H06CA6351 ,&H14292967 , _
      &H27B70A85 ,&H2E1B2138 ,&H4D2C6DFC ,&H53380D13 ,&H650A7354 ,&H766A0ABB ,&H81C2C92E ,&H92722C85 , _
      &HA2BFE8A1 ,&HA81A664B ,&HC24B8B70 ,&HC76C51A3 ,&HD192E819 ,&HD6990624 ,&HF40E3585 ,&H106AA070 , _
      &H19A4C116 ,&H1E376C08 ,&H2748774C ,&H34B0BCB5 ,&H391C0CB3 ,&H4ED8AA4A ,&H5B9CCA4F ,&H682E6FF3 , _
      &H748F82EE ,&H78A5636F ,&H84C87814 ,&H8CC70208 ,&H90BEFFFA ,&HA4506CEB ,&HBEF9A3F7 ,&HC67178F2}
      
   Dim As UByte Ptr where = inpt
   For i = 0 To 15
      Dim As UInteger temp = inpt[(4 *i)]
      temp Shl= 8
      temp Or= inpt[(4 *i) + 1]
      temp Shl= 8
      temp Or= inpt[(4 *i) + 2]
      temp Shl= 8
      temp Or= inpt[(4 *i) + 3]
      w(i) = temp
   Next
   
   For i = 16 To 63
      w(i) = (SHA256_01(W(i - 2)) + W(i - 7) + SHA256_00(W(i - 15)) + W(i - 16))
   Next
   
   a = state(0)
   b = state(1)
   c = state(2)
   d = state(3)
   e = state(4)
   f = state(5)
   g = state(6)
   h = state(7)
   
      for i = 0 To 63
         T1 = H            + SHA256_E1(E) + SHA256_Ch(E ,F ,G) + K(i) + W(i)
         T2 = SHA256_E0(A) + SHA256_Maj(A ,B ,C)
         H  = G
         G  = F
         F  = E
         E  = D + T1
         D  = C
         C  = B
         B  = A
         A  = T1 + T2
      Next
   
   state(0) += a
   state(1) += b
   state(2) += c
   state(3) += d
   state(4) += e
   state(5) += f
   state(6) += g
   state(7) += h
   
End Sub
Sub SHA256Checksum.Update(byval dat As UByte Ptr ,byval length As ULongInt)
   Dim As ULongInt i ,index ,part_len
   index = Cast(ULongInt ,(count(0) Shr 3) And &H3F)
   count(0) += (length Shl 3)
   If (count(0) < (length Shl 3)) Then
      count(1) += 1
   EndIf
   count(1) += (length Shr 29)
   part_len = 64 - index
   
   If (length >= part_len) Then
      memcpy(@buf(index) ,dat ,part_len)
      Transform(@buf(0))
      i = part_len
      While i + 63 < length
         Transform(@dat[i])
         i += 64
      Wend
      index = 0
   Else
      i = 0
   EndIf
   memcpy(@buf(index) ,@dat[i] ,length - i)
End Sub

Function SHA256Checksum.Final() As String
  Dim As UByte PADDING(64) => {&H80}
  Dim As UByte bits(8)
  Dim As ULongInt index, pad_len, t
  Dim As ULongInt i
  t = count(0)
  bits( 7) = t:t Shr= 8
  bits( 6) = t:t Shr= 8
  bits( 5) = t:t Shr= 8
  bits( 4) = t
  t = count(1)
  bits( 3) = t:t Shr= 8
  bits( 2) = t:t Shr= 8
  bits( 1) = t:t Shr= 8
  bits( 0) = t
  
  index = Cast(ULongInt, (count(0) Shr 3) And &H3f)
  pad_len = IIf(index < 56, (56 - index), (120 - index))
  Update(@PADDING(0), pad_len)
  
  Update(@bits(0), 8)
  
  Dim As String ret
   For i = 0 To 7
     ret += Hex(state(i), 8)
   Next
   
  Return ret
End Function

Function SHA256createUbyte(Data_ As UByte Ptr ,nLength As ULongInt) As String Export
   If nLength = 0  Then Return ""'"No Data given"
   if Data_ = NULL Then Return ""'"Error Data address"
   Dim As SHA256Checksum HHSHA256
   For i As ULongInt = 0 To nLength -1 Step 16384 -1
      if i > 1 Then
         HHSHA256.Update((Data_ + ((i) \ 16384) * 16384) ,16384)
         i = i + 1
      End If
   Next
   HHSHA256.Update((Data_ + (nlength \ 16384) * 16384) ,nlength Mod 16384)
   Return HHSHA256.Final()
End Function

Function SHA256create(ByRef text As String) As String Export
   Dim As ULongInt nLength = Len(text)
   If nLength = 0 Then Return  ""'"No text given"
   Dim As SHA256Checksum HHSHA256
   For i As ULongInt = 0 To nLength -1 Step 16384 -1
      if i > 1 Then
         HHSHA256.Update((Cast(UByte Ptr ,StrPtr(text)) + ((i) \ 16384) * 16384) ,16384)
         i = i + 1
      End If
   Next
   HHSHA256.Update((Cast(UByte Ptr ,StrPtr(text)) + (nlength \ 16384) * 16384) ,nlength Mod 16384)
   Return HHSHA256.Final()
End Function

Function SHA256createFile(ByRef file As String) As String Export
  Dim As ULongInt nLength = Len(file)
  If nLength = 0 Then
    Return ""'"No file specified"
  EndIf
  
  Dim As Integer FFF = FreeFile
  If Open(file For Binary Access Read As #FFF) <> 0 Then
    Return ""'"File not found/can't be opened"
  EndIf
  
  Dim As ULongInt  fileLength = Lof(FFF)
  If fileLength = 0 Then
    Close #FFF
    Return ""'"Empty file"
  EndIf
  Dim As UByte buffer(16384)
  Dim As ULongInt  toBuffer
  Dim As SHA256Checksum HHSHA256
  Do Until fileLength = 0
    If fileLength >= 16384 Then
      fileLength -= 16384
      toBuffer = 16384
    Else
      toBuffer = fileLength
      fileLength = 0
    EndIf
    Get #FFF , ,buffer(0) ,toBuffer
     
    HHSHA256.Update(@buffer(0), toBuffer)
  Loop
  Close #FFF 
  Return HHSHA256.Final()
End Function