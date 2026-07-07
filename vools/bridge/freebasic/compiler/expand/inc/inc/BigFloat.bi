Extern "c"
'Declare Function __builtin_clz (Byval x As Ulong) As Long
Declare Function __builtin_sadd_overflow(Byval As Long, Byval As Long, Byref As Long) As Boolean
Declare Function __builtin_saddll_overflow(Byval As Longint, Byval As Longint, Byref As Longint) As Boolean
Declare Function __builtin_uadd_overflow(Byval As Ulong, Byval As Ulong, Byref As Ulong)         As Boolean
Declare Function __builtin_uaddll_overflow(Byval As Ulongint, Byval As Ulongint, Byref As Ulongint) As Boolean

Declare Function __builtin_ssub_overflow(Byval As Long, Byval As Long, Byref As Long) As Boolean
Declare Function __builtin_ssubll_overflow(Byval As Longint, Byval As Longint, Byref As Longint) As Boolean
Declare Function __builtin_usub_overflow(Byval As Ulong, Byval As Ulong, Byref As Ulong)         As Boolean
Declare Function __builtin_usubll_overflow(Byval As Ulongint, Byval As Ulongint, Byref As Ulongint) As Boolean

Declare Function __builtin_smul_overflow(Byval As Long, Byval As Long, Byref As Long) As Boolean
Declare Function __builtin_smulll_overflow(Byval As Longint, Byval As Longint, Byref As Longint) As Boolean
Declare Function __builtin_umul_overflow(Byval As Ulong, Byval As Ulong, Byref As Ulong)         As Boolean
Declare Function __builtin_umulll_overflow(Byval As Ulongint, Byval As Ulongint, Byref As Ulongint) As Boolean
End Extern

#ifndef NUMBER_OF_DIGITS
   Const NUMBER_OF_DIGITS = 128
#Endif

Const NUMBER_OF_BITS = NUMBER_OF_DIGITS * 3.321928094887362

#If (NUMBER_OF_BITS Mod 32) <> 0
   Const NUM_BITS = (NUMBER_OF_BITS \ 32 + 1) * 32
#Else
   Const NUM_BITS = NUMBER_OF_BITS
#Endif
#ifndef NUM_DWORDS
   Const NUM_DWORDS = NUM_BITS \ 32
#endif
#ifndef float_BIAS
   #define float_BIAS             1073741824 '2 ^ 30
#endif
'Const float_BIAS = 1073741824 '2 ^ 30

' Error definitions

#Define DIVZ_ERR        1                    'Divide by zero
#Define EXPO_ERR        2                    'Exponent overflow error
#Define EXPU_ERR        3                    'Exponent underflow error

Type BigFloat_struct
   Declare Constructor()
   Declare Constructor(Byref rhs As BigFloat_struct)
   Declare Destructor()
   Declare Operator Let(Byref rhs As BigFloat_struct)
   As Short sign
   As Ulong exponent
   Union
   As Ulong Ptr mantissa
   As Ushort Ptr wmantissa
   End Union
End Type

Constructor BigFloat_struct ( )
   If This.mantissa<>0 Then
      'Print "pointer is not 0"
      'End(1)
      Return 
   End If
   This.mantissa=CAllocate((NUM_DWORDS +1), 4)
   If This.mantissa=0 Then
      'Print "unable to allocate memory"
      'End(4)
      Return
   End If
   This.sign=0
   This.exponent=0
End Constructor

Constructor BigFloat_struct(Byref rhs As BigFloat_struct)
   If This.mantissa <> 0 Then
      'Print "pointer is not 0"
      'End(1)
      Return
   End If
   This.mantissa = CAllocate((NUM_DWORDS + 1), 4)
   If This.mantissa = 0 Then
      'Print "unable to allocate memory"
      'End(4)
      Return
   End If
   this.sign     = rhs.sign
   this.exponent = rhs.exponent
   For i As Long = 0 To NUM_DWORDS
      this.mantissa[i] = rhs.mantissa[i]
   Next
End Constructor

Operator BigFloat_struct.let ( Byref rhs As BigFloat_struct )
   this.sign=rhs.sign
   this.exponent=rhs.exponent
   For i As Long=0 To NUM_DWORDS
      this.mantissa[i]=rhs.mantissa[i]
   Next
End Operator

Destructor BigFloat_struct ( )
   If this.mantissa=0 Then
      'Print "unable to de-allocate memory"
      'End(-4)
      Return
   Else
      Deallocate(this.mantissa)
   End If
   this.mantissa=0
End Destructor

Type BigFloat
   Declare Constructor ( )
   Declare Constructor ( Byval rhs As Long )
   Declare Constructor ( Byval rhs As Double )
   Declare Constructor ( Byref rhs As String )
   Declare Constructor ( Byref rhs As BigFloat )
   Declare Destructor ( )
   
   Declare Operator Let ( Byval rhs As Long )
   Declare Operator Let ( Byval rhs As Double )
   Declare Operator Let ( Byref rhs As String )
   Declare Operator Let ( Byref rhs As BigFloat )
   Declare Operator Cast ( ) As String
   Declare Operator Cast ( ) As Long
   Declare Operator Cast ( ) As Double
   
   '----------------------------------------------
   Declare Operator += (Byref rhs As BigFloat)
   Declare Operator += (Byval rhs As Long)
   Declare Operator += (Byval rhs As Double)
   Declare Operator += (Byref rhs As String)
   Declare Operator -= (Byref rhs As BigFloat)
   Declare Operator -= (ByVal rhs As Long)
   Declare Operator -= (Byval rhs As Double)
   Declare Operator -= (Byref rhs As String)
   Declare Operator *= (Byref rhs As BigFloat)
   Declare Operator *= (Byval rhs As Long)
   Declare Operator *= (Byval rhs As Double)
   Declare Operator *= (Byref rhs As String)
   Declare Operator /= (Byref rhs As BigFloat)
   Declare Operator /= (Byval rhs As Long)
   Declare Operator /= (Byval rhs As Double)
   Declare Operator /= (Byval rhs As Single)
   Declare Operator /= (Byref rhs As String)

   ' For Next Implicit step = +1
   Declare Operator For ( )
   Declare Operator Step( )
   Declare Operator Next( Byref end_cond As BigFloat ) As Integer
   ' For Next Exlicit step
   Declare Operator For ( Byref stp As BigFloat )
   Declare Operator Step( Byref stp As BigFloat )
   Declare Operator Next( Byref end_cond As BigFloat, Byref step_var As BigFloat ) As Integer
   
   Declare Function toString( ByVal places As Long=NUM_DWORDS*9.63 ) As String
   Declare Function toLong ( ) As Long
   Declare Function toDouble ( ) As Double

   BigNum As BigFloat_struct

End Type

Declare Function fpcmp(Byref x As BigFloat_struct, Byref y As BigFloat_struct, Byval dwords As Long=NUM_DWORDS) As Long
Declare Function fpadd(Byref x As BigFloat_struct, Byref y As BigFloat_struct, Byval dwords As Long=NUM_DWORDS) As BigFloat_struct
Declare Function fpsub(Byref x As BigFloat_struct, Byref y As BigFloat_struct, Byval dwords As Long=NUM_DWORDS) As BigFloat_struct
Declare Function fpmul(Byref x As BigFloat_struct, Byref y As BigFloat_struct, Byval dwords As Long=NUM_DWORDS) As BigFloat_struct
Declare Function fpmul_si(Byref x As BigFloat_struct, Byval y As Long, Byval dwords As Long=NUM_DWORDS) As BigFloat_struct
Declare Function fpdiv_si(Byref num As BigFloat_struct, Byval den As Long, Byval dwords As Long=NUM_DWORDS) As BigFloat_struct
Declare Function fpdiv(Byref x As BigFloat_struct, Byref y As BigFloat_struct, Byval dwords As Long=NUM_DWORDS) As BigFloat_struct
Declare Function fpipow(Byref x As BigFloat_struct, Byval e As Longint, Byval dwords As Long=NUM_DWORDS) As BigFloat_struct
Declare Function dbl2fp(Byval x As Double) As BigFloat_struct
Declare Function fp2dbl(Byref x As BigFloat_struct) As Double
Declare Function ui2fp(Byval m As Ulong, Byval dwords As Long=NUM_DWORDS) As BigFloat_struct
Declare Function fp2ui(Byref x As BigFloat_struct, Byval dwords As Long=NUM_DWORDS) As Ulong
Declare Function si2fp(Byval m As Long, Byval dwords As Long=NUM_DWORDS) As BigFloat_struct
Declare Function fp2si(Byref x As BigFloat_struct, Byval dwords As Long=NUM_DWORDS) As Long
Declare Function str2fp(ByRef x As String) As BigFloat_struct
Declare Function fp2str(ByRef zz As BigFloat_struct, ByVal digits As Long=NUMBER_OF_DIGITS+8) As String
Declare Function fpfix( Byref num As BigFloat_struct, Byref jj As Long=0 ) As BigFloat_struct
Declare Function fpfrac( ByRef num As BigFloat_struct ) As BigFloat_struct
Declare Function fpsqr (Byref num As bigfloat_struct, Byval dwords As Long=NUM_DWORDS) As bigfloat_struct
Declare Function mp_sin(Byref x As BigFloat_struct, Byval dwords As Ulong = NUM_DWORDS) As BigFloat_struct
Declare Function mp_cos (Byref x As BigFloat_struct, Byval dwords As Ulong = NUM_DWORDS) As BigFloat_struct
Declare Function mp_tan(Byref x As BigFloat_struct, Byval dwords As Ulong = NUM_DWORDS) As BigFloat_struct
Declare Function fpatn (Byref x As BigFloat_struct, Byval dwords As Ulong = NUM_DWORDS) As BigFloat_struct
Declare Function fpasin (Byref x As BigFloat_struct, Byval dwords As Ulong = NUM_DWORDS) As BigFloat_struct
Declare Function fpacos (ByRef x As BigFloat_struct, ByVal dwords As ULong = NUM_DWORDS) As BigFloat_struct
Declare Function fpnroot(Byref x As BigFloat_struct, Byval p As Long, Byval dwords As Long=NUM_DWORDS) As BigFloat_struct
Declare Function fplog (x As BigFloat_struct, Byval dwords As Long=NUM_DWORDS) As BigFloat_struct
Declare Function fpexp (Byref x As BigFloat_struct, Byval dwords As Long=NUM_DWORDS) As BigFloat_struct

Function Bigfloat.toString( Byval places As Long=NUM_DWORDS*9.63 ) As String
   Function = fp2str( this.BigNum, places )
End Function

Function Bigfloat.toLong ( ) As Long
   Dim As Double x
   x=fp2dbl(this.BigNum)
   Return Clng(x)
End Function


Function Bigfloat.toDouble ( ) As Double
   Function = fp2dbl(this.BigNum)
End Function

Constructor Bigfloat ( )
   this.BigNum=si2fp(0, NUM_DWORDS)
End Constructor

Constructor Bigfloat ( Byval rhs As Long )
   this.BigNum=si2fp( rhs, NUM_DWORDS )
End Constructor

Constructor Bigfloat ( Byref rhs As String )
   this.BigNum=str2fp( rhs )
End Constructor

Constructor Bigfloat ( Byref rhs As Bigfloat)
   this.BigNum.sign=rhs.BigNum.sign
   this.BigNum.exponent=rhs.BigNum.exponent
   For i As Long=0 To NUM_DWORDS
      this.BigNum.mantissa[i]=rhs.BigNum.mantissa[i]
   Next
End Constructor

Constructor Bigfloat ( Byval rhs As Double )
   this.BigNum=dbl2fp( rhs )
End Constructor

Operator Bigfloat.let ( Byref rhs As Bigfloat )
   this.BigNum.sign=rhs.BigNum.sign
   this.BigNum.exponent=rhs.BigNum.exponent
   For i As Long=0 To NUM_DWORDS
      this.BigNum.mantissa[i]=rhs.BigNum.mantissa[i]
   Next
End Operator

Operator Bigfloat.let ( Byval rhs As Long )
   this.BigNum=si2fp( rhs, NUM_DWORDS )
End Operator

Operator Bigfloat.let ( Byref rhs As String )
   this.BigNum=str2fp( rhs )
End Operator

Operator Bigfloat.Let ( Byval rhs As Double )
   this.BigNum=dbl2fp( rhs )
End Operator

Operator Bigfloat.cast ( ) As String
   Operator = fp2str(this.BigNum)
End Operator

Operator Bigfloat.cast ( ) As Long
   Dim As Double x
   x=fp2dbl(this.BigNum)
   Operator = Clng(x)
End Operator

Operator Bigfloat.cast ( ) As Double
   Operator = fp2dbl(this.BigNum)
End Operator

Destructor Bigfloat ( )
End Destructor

'============================================================================

Operator BigFloat.for ( )
End Operator
 
Operator BigFloat.step ( )
   this.BigNum = fpadd(this.BigNum,si2fp(1, NUM_DWORDS), NUM_DWORDS)
End Operator 
 
Operator BigFloat.next ( Byref end_cond As BigFloat ) As Integer
   Return fpcmp(This.BigNum, end_cond.BigNum, NUM_DWORDS)<=0
End Operator
 
 
'' explicit step versions
'' 
Operator BigFloat.for ( Byref step_var As BigFloat )
End Operator
 
Operator BigFloat.step ( Byref step_var As BigFloat )
   this.BigNum = fpadd(this.BigNum, step_var.BigNum, NUM_DWORDS)   
End Operator 
 
Operator BigFloat.next ( Byref end_cond As BigFloat, Byref step_var As BigFloat ) As Integer
   If fpcmp(step_var.BigNum, si2fp(0, NUM_DWORDS), NUM_DWORDS) < 0 Then
      Return fpcmp(This.BigNum, end_cond.BigNum, NUM_DWORDS) >= 0
   Else
      Return fpcmp(This.BigNum, end_cond.BigNum, NUM_DWORDS) <= 0
   End If
End Operator

'============================================================================

Operator + ( Byref lhs As Bigfloat, Byval rhs As Bigfloat ) As Bigfloat
   Dim As Bigfloat result
   result.BigNum= fpadd(lhs.BigNum, rhs.BigNum, NUM_DWORDS)
   Operator = result
End Operator

Operator + ( Byref lhs As Bigfloat, Byval rhs As Double ) As Bigfloat
   Dim As Bigfloat result
   result.BigNum=dbl2fp( rhs )
   result.BigNum= fpadd(lhs.BigNum, result.BigNum, NUM_DWORDS)
   Operator = result
End Operator

Operator + ( Byval lhs As Double, Byref rhs As Bigfloat ) As Bigfloat
   Dim As Bigfloat result
   result.BigNum=dbl2fp( lhs )
   result.BigNum= fpadd( result.BigNum, rhs.BigNum, NUM_DWORDS)
   Operator = result
End Operator

Operator + ( Byref lhs As Bigfloat, Byval rhs As Long ) As Bigfloat
   Dim As Bigfloat result
   result.BigNum=si2fp( rhs )
   result.BigNum= fpadd(lhs.BigNum, result.BigNum, NUM_DWORDS)
   Operator = result
End Operator

Operator + ( Byval lhs As Long, Byref rhs As Bigfloat ) As Bigfloat
   Dim As Bigfloat result
   result.BigNum=si2fp( lhs )
   result.BigNum= fpadd( result.BigNum, rhs.BigNum, NUM_DWORDS)
   Operator = result
End Operator

Operator + (Byref lhs As Bigfloat, Byref rhs As String) As Bigfloat
   Dim As Bigfloat result
   result.BigNum=str2fp(rhs)
   result.BigNum= fpadd(lhs.BigNum, result.BigNum, NUM_DWORDS)
   Operator = result
End Operator

Operator - ( Byref rhs As Bigfloat ) As Bigfloat
   Dim As Bigfloat result = rhs
   result.BigNum.sign = result.BigNum.sign Xor &h8000
   Operator = result
End Operator

Operator - ( Byref lhs As Bigfloat, Byval rhs As Bigfloat ) As Bigfloat
   Dim As Bigfloat result
   result.BigNum= fpsub(lhs.BigNum, rhs.BigNum, NUM_DWORDS)
   Operator = result
End Operator

Operator - ( Byref lhs As Bigfloat, Byval rhs As Double ) As Bigfloat
   Dim As Bigfloat result
   result.BigNum=dbl2fp( rhs )
   result.BigNum= fpsub(lhs.BigNum, result.BigNum, NUM_DWORDS)
   Operator = result
End Operator

Operator - ( Byval lhs As Double, Byref rhs As Bigfloat ) As Bigfloat
   Dim As Bigfloat result
   result.BigNum=dbl2fp( lhs )
   result.BigNum= fpsub( result.BigNum, rhs.BigNum, NUM_DWORDS)
   Operator = result
End Operator

Operator - ( Byref lhs As Bigfloat, Byval rhs As Long ) As Bigfloat
   Dim As Bigfloat result
   result.BigNum=si2fp(rhs, NUM_DWORDS)
   result.BigNum= fpsub(lhs.BigNum, result.BigNum, NUM_DWORDS)
   Operator = result
End Operator

Operator - ( Byval lhs As Long, Byref rhs As Bigfloat  ) As Bigfloat
   Dim As Bigfloat result
   result.BigNum=si2fp(lhs, NUM_DWORDS)
   result.BigNum= fpsub(result.BigNum, rhs.BigNum, NUM_DWORDS)
   Operator = result
End Operator

Operator - (Byref lhs As Bigfloat, Byref rhs As String) As Bigfloat
   Dim As Bigfloat result
   result.BigNum=str2fp(rhs)
   result.BigNum= fpsub(lhs.BigNum, result.BigNum, NUM_DWORDS)
   Operator = result
End Operator

Operator * ( Byref lhs As Bigfloat, Byval rhs As Bigfloat ) As Bigfloat
   Dim As Bigfloat result
   result.BigNum= fpmul(lhs.BigNum, rhs.BigNum, NUM_DWORDS)
   Operator = result
End Operator

Operator * ( Byref lhs As Bigfloat, Byval rhs As Double ) As Bigfloat
   Dim As Bigfloat result
   result.BigNum=dbl2fp( rhs )
   result.BigNum= fpmul(lhs.BigNum, result.BigNum, NUM_DWORDS)
   Operator = result
End Operator

Operator * ( Byval lhs As Double, Byref rhs As Bigfloat ) As Bigfloat
   Dim As Bigfloat result
   result.BigNum=dbl2fp( lhs )
   result.BigNum= fpmul( result.BigNum, rhs.BigNum, NUM_DWORDS)
   Operator = result
End Operator

Operator * ( Byref lhs As Bigfloat, Byval rhs As Long ) As Bigfloat
   Dim As Bigfloat result
   result.BigNum=si2fp(rhs, NUM_DWORDS)
   result.BigNum= fpmul(result.BigNum, lhs.BigNum, NUM_DWORDS)
   Operator = result
End Operator

Operator * ( Byval lhs As Long, Byref rhs As Bigfloat  ) As Bigfloat
   Dim As Bigfloat result
   result.BigNum=si2fp(lhs, NUM_DWORDS)
   result.BigNum= fpmul(result.BigNum, rhs.BigNum, NUM_DWORDS)
   Operator = result
End Operator

Operator * (Byref lhs As Bigfloat, Byref rhs As String) As Bigfloat
   Dim As Bigfloat result
   result.BigNum=str2fp(rhs)
   result.BigNum= fpmul(lhs.BigNum, result.BigNum, NUM_DWORDS)
   Operator = result
End Operator

Operator / ( Byref lhs As Bigfloat, Byval rhs As Bigfloat ) As Bigfloat
   Dim As Bigfloat result
   result.BigNum= fpdiv(lhs.BigNum, rhs.BigNum, NUM_DWORDS)
   Operator = result
End Operator

Operator / ( Byref lhs As Bigfloat, Byval rhs As Double ) As Bigfloat
   Dim As Bigfloat result
   result.BigNum=dbl2fp( rhs )
   result.BigNum= fpdiv(lhs.BigNum, result.BigNum, NUM_DWORDS)
   Operator = result
End Operator

Operator / ( Byval lhs As Double, Byref rhs As Bigfloat ) As Bigfloat
   Dim As Bigfloat result
   result.BigNum=dbl2fp( lhs )
   result.BigNum= fpdiv( result.BigNum, rhs.BigNum, NUM_DWORDS)
   Operator = result
End Operator

Operator / ( Byref lhs As Bigfloat, Byval rhs As Long ) As Bigfloat
   Dim As Bigfloat result
   result.BigNum=si2fp(rhs, NUM_DWORDS)
   result.BigNum= fpdiv(lhs.BigNum, result.BigNum, NUM_DWORDS)
   Operator = result
End Operator

Operator / ( Byval lhs As Long, Byref rhs As Bigfloat  ) As Bigfloat
   Dim As Bigfloat result
   result.BigNum=si2fp(lhs, NUM_DWORDS)
   result.BigNum= fpdiv(result.BigNum, rhs.BigNum, NUM_DWORDS)
   Operator = result
End Operator

Operator / (Byref lhs As Bigfloat, Byref rhs As String) As Bigfloat
   Dim As Bigfloat result
   result.BigNum=str2fp(rhs)
   result.BigNum= fpdiv(lhs.BigNum, result.BigNum, NUM_DWORDS)
   Operator = result
End Operator

Operator ^ ( Byref lhs As Bigfloat, Byval rhs As Longint ) As Bigfloat
   Dim As Bigfloat lhs2
   lhs2.BigNum=fpipow(lhs.BigNum, rhs, NUM_DWORDS)
   Operator = lhs2
End Operator

Operator ^ ( Byref lhs As Bigfloat, Byref rhs As Bigfloat ) As Bigfloat
   Dim As Bigfloat lhs2
   lhs2.BigNum=fplog(lhs.BigNum, NUM_DWORDS)
   lhs2.BigNum=fpmul(lhs2.BigNum, rhs.BigNum, NUM_DWORDS)
   lhs2.BigNum=fpexp(lhs2.BigNum, NUM_DWORDS)
   Operator = lhs2
End Operator

Operator BigFloat.+= (Byref rhs As BigFloat)
   this.BigNum = fpadd(this.BigNum, rhs.BigNum, NUM_DWORDS)
End Operator

Operator BigFloat.+= (Byval rhs As Long)
   Dim As BigFloat result
   result.BigNum=si2fp(rhs, NUM_DWORDS)
   this.BigNum = fpadd(this.BigNum, result.BigNum, NUM_DWORDS)
End Operator

Operator BigFloat.+= (Byval rhs As Double)
   Dim As BigFloat result
   result.BigNum=dbl2fp( rhs )
   this.BigNum = fpadd(this.BigNum, result.BigNum, NUM_DWORDS)
End Operator

Operator BigFloat.+= (Byref rhs As String)
   Dim As BigFloat result
   result.BigNum=str2fp(rhs)
   this.BigNum = fpadd(this.BigNum, result.BigNum, NUM_DWORDS)
End Operator

Operator BigFloat.-= (Byref rhs As BigFloat)
   this.BigNum = fpsub(this.BigNum, rhs.BigNum, NUM_DWORDS)
End Operator

Operator BigFloat.-= (Byval rhs As Long)
   Dim As BigFloat result
   result.BigNum=si2fp(rhs, NUM_DWORDS)
   this.BigNum = fpsub(this.BigNum, result.BigNum, NUM_DWORDS)
End Operator

Operator BigFloat.-= (Byval rhs As Double)
   Dim As BigFloat result
   result.BigNum=dbl2fp( rhs )
   this.BigNum = fpsub(this.BigNum, result.BigNum, NUM_DWORDS)
End Operator

Operator BigFloat.-= (Byref rhs As String)
   Dim As BigFloat result
   result.BigNum=str2fp(rhs)
   this.BigNum = fpsub(this.BigNum, result.BigNum, NUM_DWORDS)
End Operator

Operator BigFloat.*= (Byref rhs As BigFloat)
   this.BigNum = fpmul(this.BigNum, rhs.BigNum, NUM_DWORDS)
End Operator

Operator BigFloat.*= (Byval rhs As Long)
   Dim As BigFloat result
   result.BigNum=si2fp(rhs, NUM_DWORDS)
   this.BigNum = fpmul(this.BigNum, result.BigNum, NUM_DWORDS)
End Operator

Operator BigFloat.*= (Byval rhs As Double)
   Dim As BigFloat result
   result.BigNum=dbl2fp( rhs )
   this.BigNum = fpmul(this.BigNum, result.BigNum, NUM_DWORDS)
End Operator

Operator BigFloat.*= (Byref rhs As String)
   Dim As BigFloat result
   result.BigNum=str2fp(rhs)
   this.BigNum = fpmul(this.BigNum, result.BigNum, NUM_DWORDS)
End Operator

Operator BigFloat./= (Byref rhs As BigFloat)
   this.BigNum = fpdiv(this.BigNum, rhs.BigNum, NUM_DWORDS)
End Operator

Operator BigFloat./= (Byval rhs As Long)
   Dim As BigFloat result
   result.BigNum=si2fp(rhs, NUM_DWORDS)
   this.BigNum = fpdiv(this.BigNum, result.BigNum, NUM_DWORDS)
End Operator

Operator BigFloat./= (Byval rhs As Double)
   Dim As BigFloat result
   result.BigNum=dbl2fp( rhs )
   this.BigNum = fpdiv(this.BigNum, result.BigNum, NUM_DWORDS)
End Operator

Operator BigFloat./= (Byref rhs As String)
   Dim As BigFloat result
   result.BigNum=str2fp(rhs)
   this.BigNum = fpdiv(this.BigNum, result.BigNum, NUM_DWORDS)
End Operator

Operator = ( Byref lhs As BigFloat, Byref rhs As BigFloat ) As Long
   Operator = fpcmp(lhs.BigNum, rhs.BigNum, NUM_DWORDS)=0
End Operator

Operator < ( Byref lhs As BigFloat, Byref rhs As BigFloat ) As Long
   Operator = fpcmp(lhs.BigNum, rhs.BigNum, NUM_DWORDS)<0
End Operator

Operator > ( Byref lhs As BigFloat, Byref rhs As BigFloat ) As Long
   Operator = fpcmp(lhs.BigNum, rhs.BigNum, NUM_DWORDS)>0
End Operator

Operator <= ( Byref lhs As BigFloat, Byref rhs As BigFloat ) As Long
   Operator = fpcmp(lhs.BigNum, rhs.BigNum, NUM_DWORDS)<=0
End Operator

Operator >= ( Byref lhs As BigFloat, Byref rhs As BigFloat ) As Long
   Operator = fpcmp(lhs.BigNum, rhs.BigNum, NUM_DWORDS)>=0
End Operator

Operator <> ( Byref lhs As BigFloat, Byref rhs As BigFloat ) As Long
   Operator = fpcmp(lhs.BigNum, rhs.BigNum, NUM_DWORDS)<>0
End Operator

Operator Abs(Byref rhs As BigFloat) As BigFloat
   Dim As BigFloat result
   result.BigNum=rhs.BigNum
   result.BigNum.sign = 0
   Operator = result
End Operator

Operator  Fix (Byref x As BigFloat) As BigFloat
   Dim As BigFloat result
   result.BigNum =fpfix(x.BigNum)
   Operator = result
End Operator

Operator Frac(Byref x As BigFloat) As BigFloat
   Dim As BigFloat result
   result.BigNum=fpfrac(x.BigNum)
   Operator = result
End Operator

Operator Sqr(Byref x As BigFloat) As BigFloat
   Dim As BigFloat result
   result.BigNum=fpsqr(x.BigNum)
   Operator = result
End Operator

Operator Sin(Byref x As BigFloat) As BigFloat
   Dim As BigFloat result
   result.BigNum=mp_sin(x.BigNum)
   Operator = result
End Operator

Operator Cos(Byref x As BigFloat) As BigFloat
   Dim As BigFloat result
   result.BigNum=mp_cos(x.BigNum)
   Operator = result
End Operator

Operator Tan(Byref x As BigFloat) As BigFloat
   Dim As BigFloat result
   result.BigNum=mp_tan(x.BigNum)
   Operator = result
End Operator

Operator Atn(Byref x As BigFloat) As BigFloat
   Dim As BigFloat result
   result.BigNum=fpatn(x.BigNum)
   Operator = result
End Operator

Operator Asin(Byref x As BigFloat) As BigFloat
   Dim As BigFloat result
   result.BigNum=fpasin(x.BigNum)
   Operator = result
End Operator

Operator Acos(Byref x As BigFloat) As BigFloat
   Dim As BigFloat result
   result.BigNum=fpacos(x.BigNum)
   Operator = result
End Operator

Operator Exp(Byref x As BigFloat) As BigFloat
   Dim As BigFloat result
   result.BigNum=fpexp(x.BigNum)
   Operator = result
End Operator

Operator Log(Byref x As BigFloat) As BigFloat
   Dim As BigFloat result
   result.BigNum=fplog(x.BigNum)
   Operator = result
End Operator

Operator Sgn(Byref x As BigFloat) As Long
   Dim As Long result
   If x<0 Then
      result=-1
   Elseif x=0 Then
      result=0
   Elseif x>0 Then
      result=1
   End If
   Operator = result
End Operator

Dim Shared As BigFloat_struct Log102
Log102.sign=0
Log102.exponent=(-2)+float_BIAS+1
If NUM_DWORDS>=0 Then Log102.mantissa[0]=&h13441350
If NUM_DWORDS>=1 Then Log102.mantissa[1]=&h9F79FEF3
If NUM_DWORDS>=2 Then Log102.mantissa[2]=&h11F12B35
If NUM_DWORDS>=3 Then Log102.mantissa[3]=&h816F922F

Private Function log2_32(ByVal value As ULong) As Long
'https://stackoverflow.com/questions/11376288/fast-computing-of-log2-for-64-bit-integers
   Static tab32(0 To 31) As Const Long = {0, 9, 1, 10, 13, 21, 2, 29, 11, 14, 16, 18, 22, 25, 3, 30, 8, 12, 20, 28, 15, 17, 24, 7, 19, 27, 23, 6, 26, 5, 4, 31}
   value Or= Culng(value Shr 1)
   value Or= Culng(value Shr 2)
   value Or= Culng(value Shr 4)
   value Or= Culng(value Shr 8)
   value Or= Culng(value Shr 16)
   Return tab32(Culng(Culng(value * &h07C4ACDD) Shr 27))
End Function

Private Function log2_64(Byval value As Ulongint) As Long
'https://stackoverflow.com/questions/11376288/fast-computing-of-log2-for-64-bit-integers
   Static tab64(0 To 63) As Const Long ={63, 0, 58, 1, 59, 47, 53, 2, 60, 39, 48, 27, 54, 33, 42, 3, 61, 51, 37, 40, 49, 18, 28, 20, 55, 30, 34, 11, 43, 14, 22, 4, 62, 57, 46, 52, 38, 26, 32, 41, 50, 36, 17, 19, 29, 10, 13, 21, 56, 45, 25, 31, 35, 16, 9, 12, 44, 24, 15, 8, 23, 7, 6, 5}
   value Or= Culngint(value Shr 1)
   value Or= Culngint(value Shr 2)
   value Or= Culngint(value Shr 4)
   value Or= Culngint(value Shr 8)
   value Or= Culngint(value Shr 16)
   value Or= Culngint(value Shr 32)
   Return tab64((Culngint((value - (value Shr 1)) * &h07EDD5E59A4E28C2) Shr 58))
End Function

Function ipower (Byval x As Ulongint, Byval e As Ulongint) As Ulongint
   'take x to an integer power
   Dim As Ulongint z, y, n
   y = x
   n = e
   z = 1
   While n > 0
      While (n And 1) = 0
         n = n \ 2
         y = y * y
      Wend
         n = n - 1
         z = y * z
   Wend
   Return z
End Function

Function shl32(Byval n As Ulong, Byval k As Ubyte, Byref c As Ulong) As Ulong
   If k>0 And k<32 Then
      Dim As Ulong carry=n
      Dim As Ubyte k32=32-k
      Asm
         mov cl, [k32]
         Shr dword Ptr [carry], cl
         mov cl, [k]
         Shl dword Ptr [n], cl
      End Asm
      c=carry
   End If
   Return n
End Function

Function shr32(Byval n As Ulong, Byval k As Ubyte, Byref c As Ulong) As Ulong
   If k>0 And k<32 Then
      Dim As Ulong carry=n
      Dim As Ubyte k32=32-k
      Asm
         mov cl, [k32]
         Shl dword Ptr [carry], cl
         mov cl, [k]
         Shr dword Ptr [n], cl
      End Asm
      c=carry
   End If
   Return n
End Function

Sub shiftl(Byref fac1 As BigFloat_struct, Byval k As Long, Byval dwords As Long=NUM_DWORDS)
   If k>0 And k<32 Then
      Dim As Integer i
      Dim As Ulong n, carry, c=0
      Dim As Long k32=32-k
      For i=dwords To 0 Step -1
         n=fac1.mantissa[i]
         carry=n
         carry=Cast(Ulong, (carry Shr k32))
         n=Cast(Ulong, (n Shl k))
         fac1.mantissa[i]=n+c
         c=carry
      Next
   Elseif k=32 Then
      Dim As Long i
      For i=0 To dwords-1
         fac1.mantissa[i]=fac1.mantissa[i+1]
      Next
      fac1.mantissa[dwords]=0
   End If
End Sub

Sub shiftr(Byref fac1 As BigFloat_struct, Byval k As Long, Byval dwords As Long=NUM_DWORDS)
   If k>0 And k<32 Then
      Dim As Long i
      Dim As Ulong n, carry, c=0
      Dim As Long k32=32-k
      For i=0 To dwords
         n=fac1.mantissa[i]
         carry=n
         carry=Cast(Ulong, (carry Shl k32))
         n=Cast(Ulong, (n Shr k))   
         fac1.mantissa[i]=c+n
         c=carry
      Next
   Elseif k=32 Then
      Dim As Integer i
      For i=dwords To 1 Step -1
         fac1.mantissa[i]=fac1.mantissa[i-1]
      Next
      fac1.mantissa[0]=0
   End If
End Sub

Function fpcmp(Byref x As BigFloat_struct, Byref y As BigFloat_struct, Byval dwords As Long=NUM_DWORDS) As Long
   If dwords>NUM_DWORDS Then dwords=NUM_DWORDS
      Dim As Long i
      Dim As Longint c
      If x.sign < y.sign Then
         Return -1
      End If
      If x.sign > y.sign Then
         Return 1
      End If
      If x.exponent<y.exponent Then
         If x.sign=0 Then
            Return -1
         Else
            Return 1
         End If
      End If
      If x.exponent>y.exponent Then
         If x.sign=0 Then
            Return 1
         Else
            Return -1
         End If
      End If

      For i=0 To dwords
         c=Clngint(x.mantissa[i])-clngint(y.mantissa[i])
         If c<>0 Then Exit For
      Next
      If c=0 Then Return 0
      If c<0 Then
         If x.sign=0 Then
            Return -1
         Else
            Return 1
         End If
      End If
      If c>0 Then
         If x.sign=0 Then
            Return 1
         Else
            Return -1
         End If
      End If
End Function

Function NORM_FAC1(Byref fac1 As BigFloat_struct, Byval dwords As Long=NUM_DWORDS) As Integer
   If dwords>NUM_DWORDS Then dwords=NUM_DWORDS
   ' normalize the number in fac1
   ' all routines exit through this one.

   'see if the mantissa is all zeros.
   'if so, set the exponent and sign equal to 0.
   Dim As Long i,er=0,f=0
   Dim As Ulong ui
   For i=0 To dwords
      If fac1.mantissa[i]>0 Then f=1
   Next
   If f=0 Then
      fac1.exponent=0
      fac1.sign=0
      Exit Function
   End If

   While fac1.mantissa[0]=0
      shiftl(fac1, 32, dwords)
      fac1.exponent-=32
      If fac1.exponent=0 Then
         NORM_FAC1=EXPU_ERR
         Exit Function
      End If
   Wend
   'i=__builtin_clz(fac1.mantissa[0])-3
   ui=fac1.mantissa[0]
   Asm
      bsr eax, dword Ptr [ui]
      mov dword Ptr [ui], eax
   End Asm
   i=(31-ui) -3
   If i>0 Then
      shiftl(fac1, i, dwords)
      fac1.exponent-=i
   End If
   'if the highmost Bit in fac1_man is nonzero,
   'shift the mantissa right 1 Bit and
   'increment the exponent      
   If fac1.mantissa[0]>(&h1ffffffful)Then
      While fac1.mantissa[0]>&h1ffffffful
      shiftr(fac1, 1, dwords)
      fac1.exponent+=1
      Wend
   Elseif fac1.mantissa[0]<&h10000000ul Then
      /' the following will probably never be executed '/
      'now shift fac1_man 1 to the left until a
      'nonzero Bit appears in the next-to-highest
      'Bit of fac1_man.  decrement exponent for
      'each shift.

      While fac1.mantissa[0]<&h10000000ul
         shiftl(fac1, 1, dwords)
         fac1.exponent-=1
      Wend
   End If

   'check for overflow/underflow
   If fac1.exponent<0 Then
   ?"NORM_FAC1 fac1.exponent<0"
   NORM_FAC1=EXPO_ERR
   End If
End Function

Function si2fp(Byval m As Long, Byval dwords As Long=NUM_DWORDS) As BigFloat_struct
   If dwords>NUM_DWORDS Then dwords=NUM_DWORDS
   Dim As BigFloat_struct fac1
   Dim As Long n=Abs(m)

   If m=0 Then
      Return fac1
   End If

   fac1.mantissa[0]=n
   NORM_FAC1(fac1, NUM_DWORDS)
   fac1.exponent=log2_32(n)+float_BIAS+1   
   If m<0 Then
      fac1.sign=&H8000
   Else
      fac1.sign=0
   End If
   Return fac1
End Function

Function ui2fp(Byval m As Ulong, Byval dwords As Long=NUM_DWORDS) As BigFloat_struct
   If dwords>NUM_DWORDS Then dwords=NUM_DWORDS
   Dim As BigFloat_struct fac1

   If m=0 Then
      Return fac1
   End If

   fac1.mantissa[0]=m
   NORM_FAC1(fac1, NUM_DWORDS)
   fac1.exponent=log2_32(m)+float_BIAS+1   
   Return fac1
End Function

Sub fpadd_aux(Byref fac1 As BigFloat_struct, Byref fac2 As BigFloat_struct, Byval dwords As Long=NUM_DWORDS)
   If dwords>NUM_DWORDS Then dwords=NUM_DWORDS
   Dim As Long c
   Dim As Integer i
   Dim As Longint v

   c=0
   For i=dwords To 1 Step -1
      v=Clngint(fac2.mantissa[i])+Clngint(fac1.mantissa[i])+c
      If v>(&h100000000ull-1) Then
         v=v-&h100000000ull
         c=1
      Else
         c=0
      End If
      fac1.mantissa[i]=v
   Next
   v=Clngint(fac1.mantissa[0])+Clngint(fac2.mantissa[0])+c
   fac1.mantissa[0]=v
   NORM_FAC1(fac1, dwords)

End Sub

Sub fpsub_aux(Byref fac1 As BigFloat_struct, Byref fac2 As BigFloat_struct, Byval dwords As Long=NUM_DWORDS)
   If dwords>NUM_DWORDS Then dwords=NUM_DWORDS
   Dim As Long c
   Dim As Integer i
   Dim As Longint v
   c=0
   For i=dwords To 1 Step -1
      v=Clngint(fac1.mantissa[i])-clngint(fac2.mantissa[i])-c
      If v<0 Then
         v=v+&h100000000ull
         c=1
      Else
         c=0
      End If
      fac1.mantissa[i]=v
   Next
   v=Clngint(fac1.mantissa[0])-clngint(fac2.mantissa[0])-c
   fac1.mantissa[0]=v
   NORM_FAC1(fac1, dwords)
End Sub

Function fpadd(Byref x As BigFloat_struct, Byref y As BigFloat_struct, Byval dwords As Long=NUM_DWORDS) As BigFloat_struct
   If dwords>NUM_DWORDS Then dwords=NUM_DWORDS

   Dim As BigFloat_struct fac1,fac2
   Dim As Long i, t, c, xsign, ysign

   xsign=x.sign:x.sign=0
   ysign=y.sign:y.sign=0
   c=fpcmp(x, y, dwords)

   x.sign=xsign
   y.sign=ysign
   If c<0 Then
      fac1=y
      fac2=x
   Else
      fac1=x
      fac2=y
   End If
   t=fac1.exponent-fac2.exponent

   If t<(NUM_BITS+32) Then
      'The difference between the two
      'exponents indicate how many times
      'we have to multiply the mantissa
      'of FAC2 by 10 (i.e., shift it right 1 place).
      'If we have to shift more times than
      'we have dwords, the result is already in FAC1.

      If t>0 And t<(NUM_BITS+32) Then 'shift

         i=t\32
         While i>0
            shiftr(fac2, 32, dwords)
            t-=32
            i-=1
         Wend
         'While t>0

         If t>0 Then   shiftr(fac2, t, dwords)
            't-=1
            'Wend
         End If
         'See if the signs of the two numbers
         'are the same.  If so, add; if not, subtract.
         If fac1.sign=fac2.sign Then 'add
            fpadd_aux(fac1,fac2, dwords)
         Else
            fpsub_aux(fac1,fac2, dwords)
         End If
   Endif
   'NORM_FAC1(fac1, dwords)
   Return fac1
End Function

Function fpsub(Byref x As BigFloat_struct, Byref y As BigFloat_struct, Byval dwords As Long=NUM_DWORDS) As BigFloat_struct
   If dwords>NUM_DWORDS Then dwords=NUM_DWORDS
   Dim As BigFloat_struct fac1,fac2
   Dim As Long s
   fac1=x
   fac2=y
   fac2.sign=fac2.sign Xor &h8000
   fac1=fpadd(fac1,fac2, dwords)
   Return fac1
End Function

Function fpmul(Byref x As BigFloat_struct, Byref y As BigFloat_struct, Byval dwords As Long=NUM_DWORDS) As BigFloat_struct
   If dwords>NUM_DWORDS Then dwords=NUM_DWORDS
   Dim As BigFloat_struct fac1,fac2
   Dim As Integer i, j, ex, er, den, num
   Dim As Ulongint digit, carry, prod ', tmp
   Dim As Ulong  fac3(0 To 2*dwords+1)

   fac1=x
   fac2=y
   'check exponents.  if either is zero,
   'the result is zero
   If fac1.exponent=0 Or fac2.exponent=0 Then 'result is zero...clear fac1.
      fac1.sign=0
      fac1.exponent=0
      For i=0 To dwords
         fac1.mantissa[i]=0
      Next
      'NORM_FAC1(fac1)
      Return fac1
   Else

      If ex<0 Then
         er=EXPO_ERR
         Return fac1 'Exit Function
      End If

      'clear fac3 mantissa
      For i=0 To dwords
         fac3(i)=0
      Next

      den=dwords
      While fac2.mantissa[den]=0
         den-=1
      Wend
      num=dwords
      While fac1.mantissa[num]=0
         num-=1
      Wend

      If num<den Then
         Swap fac1, fac2
         'fac1=y
         'fac2=x         
         Swap den, num
      End If

      For j=den To 0 Step -1
         carry=0
         digit=fac2.mantissa[j]
         For i=num To 0 Step -1
            prod=fac3(i+j+1)+digit*fac1.mantissa[i]+carry
            /'tmp=fac1.mantissa[i]
            If __builtin_umulll_overflow (digit, tmp, prod) Then Print "mul overflow"
            tmp=fac3(i+j+1)
            If __builtin_uaddll_overflow (tmp, prod, prod) Then Print "add overflow"
            If __builtin_uaddll_overflow (carry, prod, prod) Then Print "add overflow"'/
            carry=prod   Shr 32'\&H100000000
            fac3(i+j+1)=prod '(prod mod &H100000000)
         Next

         fac3(j)=carry
      Next

      For i=0 To dwords
         fac1.mantissa[i]=fac3(i)
      Next      

   End If
   'now determine exponent of result.
   'as you do...watch for overflow.
   'ex=fac2.exponent-float_BIAS+fac1.exponent
   'fac1.exponent=ex

   ex=(fac2.exponent And &h7FFFFFFFul)-float_BIAS+1
   ex=ex+(fac1.exponent And &h7FFFFFFFul)-float_BIAS+1
   fac1.exponent=ex+float_BIAS+1

   'determine the sign of the product
   fac1.sign=fac1.sign Xor fac2.sign
   NORM_FAC1(fac1, dwords)
   Return fac1
End Function

Function fpmul_si(Byref x As BigFloat_struct, Byval y As Long, Byval dwords As Long=NUM_DWORDS) As BigFloat_struct
   If dwords>NUM_DWORDS Then dwords=NUM_DWORDS
    Dim As BigFloat_struct fac1,fac2
    Dim As Integer count, ex, er, i, j
    Dim As Long n, v, c, num
    Dim As Longint carry, digit, prod, value
    fac1=x
    digit=Abs(y)
    If digit>&h7fffffff Then
      fac2=si2fp(y, dwords)
      fac1=fpmul(fac1, fac2, dwords)
      Return fac1
   End If
    'check exponents.  if either is zero,
    'the result is zero
    If fac1.exponent=0 Or y=0 Then 'result is zero...clear fac1.
        fac1.sign=0
        fac1.exponent=0
        For count=0 To dwords
            fac1.mantissa[count]=0
        Next
        NORM_FAC1(fac1, dwords)
        Return fac1
    Else
      If digit=1 Then
         If y<0 Then
            fac1.sign=fac1.sign Xor &h8000
         End If
         Return fac1
      End If
        'now determine exponent of result.
        'as you do...watch for overflow.

        If ex<0 Then
            er=EXPO_ERR
            Return fac1 'Exit Function
        End If
      num=dwords
      While fac1.mantissa[num]=0
         num-=1
      Wend        
      carry=0
         
      For i=num To 0 Step -1
         prod=digit*fac1.mantissa[i] +carry
         value=(prod Mod &h100000000)'+carry
         fac1.mantissa[i]=value
         carry=prod\&h100000000
      Next

      n=carry
'      i=__builtin_clz(n)
   Asm
      bsr eax, dword Ptr [n]
      mov dword Ptr [i], eax
   End Asm
   i=(31-i)
      shiftr(fac1, (32-i)+3)
      fac1.exponent+=(32-i+3)
      n=shl32(n, i-3,c)
      fac1.mantissa[0]+=n
    End If

    NORM_FAC1(fac1, dwords)

    If y<0 Then
      fac1.sign=fac1.sign Xor &h8000
   End If
    Return fac1
End Function

Function fpmul_ui(Byref x As BigFloat_struct, Byval y As Ulong, Byval dwords As Long=NUM_DWORDS) As BigFloat_struct
   If dwords>NUM_DWORDS Then dwords=NUM_DWORDS
    Dim As BigFloat_struct fac1,fac2
    Dim As Integer count, ex, er, i, j
    Dim As Ulong n, v, c, num
    Dim As Ulongint carry, digit, prod, value
    fac1=x
    digit=Abs(y)
    If digit>&hfffffffful Then
      fac2=si2fp(y, dwords)
      fac1=fpmul(fac1, fac2, dwords)
      Return fac1
   End If
    'check exponents.  if either is zero,
    'the result is zero
    If fac1.exponent=0 Or y=0 Then 'result is zero...clear fac1.
        fac1.sign=0
        fac1.exponent=0
        For count=0 To dwords
            fac1.mantissa[count]=0
        Next
        NORM_FAC1(fac1, dwords)
        Return fac1
    Else
      If digit=1 Then
         Return fac1
      End If
        'now determine exponent of result.
        'as you do...watch for overflow.

        If ex<0 Then
            er=EXPO_ERR
            Return fac1 'Exit Function
        End If
      num=dwords
      While fac1.mantissa[num]=0
         num-=1
      Wend        
      carry=0
         
      For i=num To 0 Step -1
         prod=digit*fac1.mantissa[i] +carry
         value=(prod Mod &h100000000)'+carry
         fac1.mantissa[i]=value
         carry=prod\&h100000000
      Next

      n=carry
      'i=__builtin_clz(n)
   Asm
      bsr eax, dword Ptr [n]
      mov dword Ptr [i], eax
   End Asm
   i=(31-i)
      shiftr(fac1, (32-i)+3)
      fac1.exponent+=(32-i+3)
      n=shl32(n, i-3,c)
      fac1.mantissa[0]+=n
    End If

    NORM_FAC1(fac1, dwords)

    Return fac1
End Function

Function fpmul_ll(Byref x As BigFloat_struct, Byval y As Longint, Byval dwords As Long=NUM_DWORDS) As BigFloat_struct
   If dwords>NUM_DWORDS Then dwords=NUM_DWORDS
    Dim As BigFloat_struct fac1,fac2
    Dim As Integer count, ex, er, i, j
    Dim As Long n, v, c
    Dim As Longint carry, digit, prod, value, n0, n1
    fac1=x
    digit=Abs(y)
    If digit>&h7FFFFFFFl And digit<=&h7FFFFFFFFFFFFFFFll Then
      n0=digit\&h100000000
      n1=digit Mod &h100000000
      fac2=fpmul_ui(fac1, n1, dwords)
      fac1.exponent+=32
      fac1=fpmul_ui(fac1, n0, dwords)
      fac1=fpadd(fac1, fac2, dwords)
      If y<0 Then fac1.sign=fac1.sign Xor &h8000
      Return fac1
   Elseif digit>&h7FFFFFFFFFFFFFFFll Then
      fac2=str2fp(Str(y))
      fac1=fpmul(fac1, fac2, dwords)
      Return fac1
   Else
      fac1=fpmul_si(fac1, Clng(y), dwords)
   End If

    If y<0 Then
      fac1.sign=fac1.sign Xor &h8000
   End If
    Return fac1
End Function

Function fpmul_ull(Byref x As BigFloat_struct, Byval y As Ulongint, Byval dwords As Long=NUM_DWORDS) As BigFloat_struct
   If dwords>NUM_DWORDS Then dwords=NUM_DWORDS
    Dim As BigFloat_struct fac1,fac2
    Dim As Integer count, ex, er, i, j
    Dim As Ulong n, v, c
    Dim As Ulongint carry, digit, prod, value, n0, n1
    fac1=x
    digit=y
    If digit>&hFFFFFFFFul Andalso digit<=&hFFFFFFFFFFFFFFFFull Then
      n0=digit\&h100000000
      n1=digit Mod &h100000000
      fac2=fpmul_ui(fac1, n1, dwords)
      fac1.exponent+=32
      fac1=fpmul_ui(fac1, n0, dwords)
      fac1=fpadd(fac1, fac2, dwords)
      Return fac1
   Elseif digit>&hFFFFFFFFFFFFFFFFull Then
      fac2=str2fp(Str(y))
      fac1=fpmul(fac1, fac2, dwords)
      Return fac1
   Else
      fac1=fpmul_ui(fac1, Culng(y), dwords)
   End If

    Return fac1
End Function

Function fpdiv_si(Byref num As BigFloat_struct, Byval den As Long, Byval dwords As Long=NUM_DWORDS) As BigFloat_struct
   If dwords>NUM_DWORDS Then dwords=NUM_DWORDS
   Dim As BigFloat_struct fac1
   Dim As Ulongint carry, remder=0
   Dim As Longint i, divisor
   Dim As Longint quotient
   Dim As Long j

   divisor=Abs(den)
   fac1=num
   If divisor=1 Then
      Return fac1
   End If
   If divisor = 0 Then
      'Print "error: divisor = 0"
      Return fac1 'Exit function
   End If
   If divisor>2147483647 Then
      'Print "error: divisor too large"
      Return fac1 'Exit function
   End If

   For i = 0 To dwords
      quotient = fac1.mantissa[i] + remder * &h100000000ull
      remder = quotient Mod divisor
      fac1.mantissa[i]=quotient \ divisor
   Next
   quotient = remder * &h100000000ull
   quotient=quotient \ divisor
   carry=fac1.mantissa[0]
   'j=__builtin_clz(fac1.mantissa[0])-3
   j=fac1.mantissa[0]
   Asm
      bsr eax, dword Ptr [j]
      mov dword Ptr [j], eax
   End Asm
   j=(31-j)-3
   If j>0 Then
      shiftl(fac1, j, dwords)
      fac1.exponent-=j
   End If

   While fac1.mantissa[0]>(&h1ffffffful)
      shiftr(fac1, 1, dwords)
      fac1.exponent+=1
   Wend
   NORM_FAC1(fac1)
   If den<0 Then
   fac1.sign=fac1.sign Xor &h8000
   End If
   Return fac1
End Function


Function fpdiv(Byref x As BigFloat_struct, Byref y As BigFloat_struct, Byval dwords As Long = NUM_DWORDS) As BigFloat_struct
   If dwords > NUM_DWORDS Then dwords = NUM_DWORDS
   
   Dim As BigFloat_struct fac1, fac2, one
   Dim As Integer         i, er, is_power_of_two
   Dim As Short           sign
   
   fac1 = x
   fac2 = y
   
   one.exponent    = (float_BIAS + 1)
   one.mantissa[0] = &H10000000ul
   one       = ui2fp(1)
   sign      = fac2.sign
   fac2.sign = 0
   If fpcmp(fac2, one) = 0 Then
      fac1.sign = fac1.sign Xor y.sign
      Return fac1
   Else
      fac2.sign = sign
   End If
   If fac2.exponent = 0 Then ' if fac2 = 0, return
      ' a divide-by-zero error and
      ' bail out.
      fac1.mantissa[i] = &H1FFFFFFFul
      For i = 1 To dwords
         fac1.mantissa[i] = &HFFFFFFFFul
      Next
      fac1.exponent = &HFFFFF + float_BIAS + 1
      er = DIVZ_ERR
      Return fac1
   Elseif fac1.exponent = 0 Then 'fact1=0, just return
      er = 0
      Return fac1
   Else
      'check to see if fac2 is a power of ten
      is_power_of_two = 0
      If fac2.mantissa[0] = &H10000000ul Then
         is_power_of_two = 1
         For i = 1 To dwords
            If fac2.mantissa[i] <> 0 Then
               is_power_of_two = 0
               Exit For
            End If
         Next
      End If
      'if fac2 is a power of ten then all we need to do is to adjust the sign and exponent and we are finished
      If is_power_of_two = 1 Then
         fac1.sign     = fac1.sign Xor fac2.sign
         fac1.exponent = fac1.exponent - fac2.exponent + float_BIAS + 1
         Return fac1
      End If
      #ifndef min
         #define min(a,b) IIf(((a)<(b)),(a),(b))
      #endif
      #Macro realw(w, j)
      ((w(j - 1) *b + w(j)) *b + w(j + 1)) *b + Iif(Ubound(w) >= j + 2, w(j + 2), 0)
      #Endmacro
      
      #Macro subtract(w, q, d, ka, kb)
      For j = ka To kb
         w(j) = w(j) - q *d(j - ka + 2)
      Next
      #Endmacro
      
      #Macro normalize(w, ka, q)
      w(ka)     = w(ka) + w(ka - 1) *b
      w(ka - 1) = q
      #Endmacro
      
      #Macro finalnorm(w, kb)
      For j = kb To 3 Step -1
         carry    = Iif(w(j) < 0, (( - w(j) - 1) \ b) + 1, Iif(w(j) >= b, - (w(j) \ b), 0))
         w(j)     = w(j)     + carry *b
         w(j - 1) = w(j - 1) - carry
      Next
      #Endmacro
      
      Dim As Double result(1 To 2 *dwords + 3), n(1 To 2 *dwords + 3), d(1 To 2 *dwords + 3)
      Const b = &H10000
      Dim As Integer j, last, laststep, q, t
      Dim As Integer stp, carry
      Dim As Double  xd, xn, rund
      Dim As Double  w(1 To Ubound(n) + 4)
      
      For j = 0 To dwords * 2 Step 2
         n(j + 3) = fac1.wmantissa[j] '\&H10000
         n(j + 2) = fac1.wmantissa[j + 1] 'Mod &H10000
         d(j + 3) = fac2.wmantissa[j] '\&H10000
         d(j + 2) = fac2.wmantissa[j + 1] 'Mod &H10000
      Next
      n(1) = (fac1.exponent And &H7FFFFFFF) - float_BIAS -1
      d(1) = (fac2.exponent And &H7FFFFFFF) - float_BIAS -1
      'For j=Ubound(n) To Ubound(w)
      '   w(j)=0
      'Next
      t    = Ubound(n) -1
      w(1) = n(1) - d(1) + 1
      w(2) = 0
      For j = 2 To Ubound(n)
         w(j + 1) = n(j)
      Next
      xd       = (d(2) *b + d(3)) *b + d(4) + d(5) / b
      laststep = t + 2
      For stp = 1 To laststep
         xn   = RealW(w, (stp + 2))
         q    = Int(xn / xd)
         last = Min(stp + t + 1, Ubound(W))
         subtract(w, q, d, (stp + 2), last)
         normalize(w, (stp + 2), q)
      Next
      FinalNorm(w, (laststep + 1))
      laststep    = Iif(w(2) = 0, laststep, laststep - 1)
      rund        = w(laststep + 1) / b
      w(laststep) = w(laststep)     + Iif(rund >= 0.5, 1, 0)
      If w(2) = 0 Then
         For j = 1 To t + 1
            result(j) = w(j + 1)
         Next
      Else
         For j = 1 To t + 1
            result(j) = w(j)
         Next
      End If
      result(1) = Iif(w(2) = 0, w(1) - 1, w(1))
      
      For j = 0 To dwords * 2 Step 2
         'fac1.mantissa[j]=result(2*j+2)*&H10000+result(2*j+3)
         fac1.wmantissa[j] = result(j + 3)
         fac1.wmantissa[j + 1] = result(j + 2)
      Next
      NORM_FAC1(fac1, dwords)
      fac1.exponent = (result(1) + BIAS)
   End If
   fac1.sign = fac1.sign Xor fac2.sign
   Return fac1
End Function

Function fpipow(Byref x As BigFloat_struct, Byval e As Longint, Byval dwords As Long=NUM_DWORDS) As BigFloat_struct
   If dwords>NUM_DWORDS Then dwords=NUM_DWORDS
   'take x to an Long power
   Dim As BigFloat_struct y=x
   Dim As BigFloat_struct z, one
   Dim As Longint n, c=0
   Dim As Integer i

   n = Abs(e)
   one.exponent=(BIAS+1)
   one.mantissa[0]=&h10000000ul
   z=one
   While n>0
      While (n And 1)=0
         n\=2
         y=fpmul(y, y, dwords)
         c+=1
      Wend
      n-=1
      z=fpmul(y, z, dwords)
      c+=1
   Wend

   If e<0 Then
      z=fpdiv(one, z, dwords)
   End If

   Return z
End Function

Function dbl2fp(Byval x As Double) As BigFloat_struct
   Dim As BigFloat_struct bf
   Dim As Ulongint n, e
   Dim As Long sign
   If x<0 Then sign=&h8000
   x=Abs(x)
   n=Peek ( Ulongint, @x )
   e=n
   n=Cast(Ulongint, (n Shl 12))
   n=Cast(Ulongint, (n Shr 4))
   n+=&h1000000000000000ull
   bf.mantissa[0]=Cast(Ulongint, (n Shr 32))
   n=e
   n=Cast(Ulongint, (n Shl 40))
   n=Cast(Ulongint, (n Shr 32))
   bf.mantissa[1]=n
   n=n+&h1000000000000000ull
   e=Cast(Ulongint, (e Shr 52))
   e=e-&h3FFul
   bf.exponent=e+BIAS+1
   bf.sign=sign
   Return bf
End Function

Function fp2dbl(Byref x As BigFloat_struct) As Double
   Dim As Double dbl
   Dim As Ulongint n, e
   Dim As Ushort ex
   Dim As Long sign
   If x.sign<>0 Then
      sign=-1
   Else
      sign=1
   End If
   If x.exponent>0 Then
      ex=(x.exponent And &h7FFFFFFF)-BIAS-1
   Else
      ex=0
   End If
   n=x.mantissa[0]
   n-=&h10000000ul
   n=Cast(Ulongint, (n Shl 24))
   e=&h3FF+ex
   e=e*&h10000000000000ull
   n=n+e
   e=x.mantissa[1]\&h100
   n=n+e
   Poke Ulongint,@dbl,n
   Return dbl*sign
End Function

Function factorial(Byval n As Ulong) As BigFloat_struct
   Dim As BigFloat_struct one, f, indx
   one.mantissa[0]=&h10000000ul
   one.exponent=0+BIAS+1
   f=one
   indx=one
   For i As Long=1 To n
      f=fpmul(f, indx)
      indx=fpadd(one, indx)
   Next
   Return f
End Function

Function factorial_ui(Byval n As Ulong) As BigFloat_struct
   Dim As BigFloat_struct one, f
   one.mantissa[0]=&h10000000ul
   one.exponent=0+BIAS+1
   f=one
   For i As Long=1 To n
      f=fpmul_si(f, i)
   Next
   Return f
End Function

Function factorial3(Byval n As Ulong) As BigFloat_struct
   Dim As BigFloat_struct one, f
   one.mantissa[0]=&h10000000ul
   one.exponent=0+BIAS+1
   f=one
   For i As Ulongint=1 To n
      f=fpmul_ull(f, i)
   Next
   Return f
End Function

Function factorial_inv(Byval n As Ulong) As BigFloat_struct
   Dim As BigFloat_struct f
   f.mantissa[0]=&h10000000ul
   f.exponent=0+BIAS+1
   For i As Long=1 To n
      f=fpdiv_si(f, i)
   Next
   Return f
End Function

Function fp2ui(Byref x As BigFloat_struct, Byval dwords As Long=NUM_DWORDS) As Ulong
   If dwords>NUM_DWORDS Then dwords=NUM_DWORDS
   Dim As BigFloat_struct fac1
   Dim As Double n
   fac1.exponent=0
   fac1.mantissa[0]=x.mantissa[0]
   n=fp2dbl(x)
   Return Fix(n)
End Function

Function fp2si(Byref x As BigFloat_struct, Byval dwords As Long=NUM_DWORDS) As Long
   If dwords>NUM_DWORDS Then dwords=NUM_DWORDS
   Dim As BigFloat_struct fac1
   Dim As Long sign
   Dim As Double n

   fac1.exponent=0
   fac1.mantissa[0]=x.mantissa[0]
   n=fp2dbl(x)
   Return Fix(n)
End Function

Function str2fp_aux(ByVal value As String, ByRef s As Long, ByRef ex As Long ) As String
   Dim As Integer j,d,e,ep,es,i,f,fp,fln
   Dim As String c,f1,f2,f3, ts
   Dim As Ulong ulng

   j=1
   s=1
   d=0
   e=0
   ep=0
   ex=0
   es=1
   i=0
   f=0
   fp=0
   f1=""
   f2=""
   f3=""
   value=Ucase(value)
   fln=Len(value)

   While j<=fln
      c=Mid(value,j,1)
      If ep=1 Then
         If c=" " Then
            j=j+1
            Continue While
         Endif
         If c="-" Then
            es=-es
            c=""
         Endif
         If c="+" Then
            j=j+1
            Continue While
         Endif
         If (c="0") And (f3="") Then
            j=j+1
            Continue While
         Endif
         If (c>"/") And (c<":") Then 'c is digit between 0 and 9
            f3=f3+c
            ex=10*ex+(Asc(c)-48)
            j=j+1
            Continue While
         Endif
      Endif

      If c=" " Then
         j=j+1
         Continue While
      Endif
      If c="-" Then
         s=-s
         j=j+1
         Continue While
      Endif
      If c="+" Then
         j=j+1
         Continue While
      Endif
      If c="." Then
         If d=1 Then
            j=j+1
            Continue While
         Endif
         d=1
      Endif
      If (c>"/") And (c<":") Then 'c is digit between 0 and 9
         If ((c="0") And (i=0)) Then
            If d=0 Then
               j=j+1
               Continue While
            Endif
            If (d=1) And (f=0) Then
               e=e-1
               j=j+1
               Continue While
            Endif
         Endif
         If d=0 Then
            f1=f1+c
            i=i+1
         Else
            If (c>"0") Then
               fp=1
            Endif
            f2=f2+c
            f=f+1
         Endif
      Endif
      If c="E" Or c="D" Then
      ep=1
      Endif
      j=j+1
   Wend
   If fp=0 Then
      f=0
      f2=""
   Endif

   If s=-1 Then s=&h8000 Else s=0

   f1=f1+f2
   f1=Mid(f1,1,1)+Right(f1,Len(f1)-1)
   fln=Len(f1)
   If fp=0 Andalso ex=0 Then
      ex=es*(fln-1)
   Else
      ex=es*((ex-1)+i+e)
   End If

   If fln>((NUM_BITS+16)*0.3010299956639811) Then
      f1=Mid(f1,1,((NUM_BITS+16)*0.3010299956639812)-1)
   Endif

   Return f1
End Function

Function str2fp(ByRef x As String) As BigFloat_struct
   Dim As Long strlenp, i, n, ex, sign, ten
   Dim As String s2, strin=x
   Dim As BigFloat_struct y, z, pw

   strin=str2fp_aux(strin, sign, ex)
   strin=Rtrim(strin,"0")
   strlenp=Len(strin)

   n=8
   ten=Valuint("1"+String(n,"0"))
   If strlenp>n Then
      s2=Left(strin, n)
      strin=Mid(strin, n+1)
   Else
      z=ui2fp(Valuint(strin))
      pw=ui2fp(10)
      pw=fpipow(pw, strlenp-ex-1)
      z=fpdiv(z, pw)
      Return z
   End If
   z=ui2fp(Valuint(s2))

   While Len(strin)>=n
      s2=Left(strin, n)
      strin=Mid(strin, n+1)
      y=ui2fp(Valuint(s2))
      z=fpmul_ui(z, ten)
      z=fpadd(z,y)
   Wend
   i=Len(strin)
   If i>0 Then
      ten=Valuint("1"+String(i,"0"))
      y=ui2fp(Valuint(strin))
      z=fpmul_ui(z, ten)
      z=fpadd(z,y)
   End If
   pw=ui2fp(10)
   pw=fpipow(pw,strlenp-ex-1)
   z=fpdiv(z, pw)
   z.sign=sign
   Return z
End Function

Function fp2str(ByRef zz As BigFloat_struct, ByVal digits As Long = NUMBER_OF_DIGITS + 8) As String

   If digits>(NUMBER_OF_DIGITS+8) Or digits<0 Then digits=NUMBER_OF_DIGITS+8
   Dim As Long ex, i, m, n, powten, sign, tn
   Dim As BigFloat_struct y, ten, tenp, z, ep, one, nine, zero
   Dim As String s, s2
   If zz.exponent=0 Then
      Return " 0"
   End If
   digits+=2
   n=8
   one=ui2fp(1)
   nine=ui2fp(9)
   ten=ui2fp(10)
   tenp=ui2fp(Clng("1"+String(n,"0")))
   tn=Clng("1"+String(n,"0"))
   z=zz
   sign=zz.sign
   z.sign=0
   If z.exponent<>0 Then
      ex=(z.exponent And &h7FFFFFFFul)-BIAS-1
   Else
      ex=0
   End If
   m=NUM_BITS-ex
   ep.exponent=-(m+16)+BIAS+1
   ep.mantissa[0]=&h10000000ul
   z=fpadd(z,ep)
   If fpcmp(z,nine)>0 Then
      While fpcmp(z,nine)>0
         z=fpdiv_si(z, 10)
         powten+=1
      Wend
   Elseif fpcmp(z,one)<0 Then
      While fpcmp(z,one)<0
         z=fpmul(z, ten)
         powten-=1
      Wend
   End If

   m=fp2ui(z)
   z=fpfrac(z)
   z=fpmul(z, tenp)
   s=Trim(Str(m))+"."
   For i=1 To digits
      If fpcmp(z, one)<0 Then
         While fpcmp(z, one)<0
            If (Len(s))>=digits Then Exit While
            z=fpmul(z, tenp)
            s=s+String(n,"0")
         Wend
      Else
         If (Len(s))>=digits Then Exit For
         y=fpfix(z)
         m=fp2ui(y)
         z=fpfrac(z)
         z=fpmul(z, tenp)
         s2=Trim(Str(m))
         s2=String(n-len(s2),"0")+s2
         s=s+s2
      End If   
   Next
   s=Ltrim(s, "0")
   If Len(s)>(digits-1) Then
      s=Left(s, digits-1)
   End If
   i=Instr(Trim(s),".")
   
   If i>2 Then
      s=Left(s,i-1)+Mid(s, i+1)
      s=Left(s,1)+"."+Mid(s, 2)
      powten+=1
   Elseif i=1 Then
      s=Mid(s,2)
      s=Left(s,1)+"."+Mid(s,2)
      powten-=1
   End If
   s2=Trim(Str(Abs(powten)))
   If (5-len(s2))>0 Then s2=String(5-len(s2),"0")+s2
   If powten<0 Then
      s2="-"+s2
   Else
      s2="+"+s2
   End If
   s=s+"e"+s2
   If sign<>0 Then
      s="-"+s
   Else
      s=" "+s
   End If
   Return s
End Function

'integer part of num
Function fpfix( Byref num As BigFloat_struct, Byref jj As Long =0 ) As BigFloat_struct
   Dim As BigFloat_struct ip
   Dim As Long ex, ex2, i, j, k, c

   ex=(num.exponent And &h7FFFFFFFul)-BIAS

   If ex<1 Then
      Return ip
   End If
   If ex>=(NUM_BITS) Then
      Return num
   End If
   ex2=ex\32

   k=ex2
   j=ex Mod 32
   jj=j

   If j>29 Then
      ex2+=1
      k=ex2
      j=0
   End If

   While ex2>0
      ex2-=1
      ip.mantissa[ex2]=num.mantissa[ex2]
   Wend

   ip.mantissa[k]=num.mantissa[k]
If jj>29 Then
   i=31-jj
   If jj=31 Then i-=1
   ip.mantissa[k]=shr32(ip.mantissa[k], (jj+i), c)
   ip.mantissa[k]=shl32(ip.mantissa[k], (jj+i), c)
Else
   ip.mantissa[k]=shr32(ip.mantissa[k], (32-j)-3, c)
   ip.mantissa[k]=shl32(ip.mantissa[k], (32-j)-3, c)
End If
   ip.exponent=ex+BIAS
   ip.sign=num.sign
   NORM_FAC1(ip)
   Return ip
End Function

'fractional part of num
Function fpfrac( Byref num As BigFloat_struct ) As BigFloat_struct
   Dim As BigFloat_struct ip, fp
   ip=fpfix(num)
   fp=fpsub(num, ip)
   Return fp
End Function

'returns 1 if integer part is odd
Function fpfix_is_odd( Byref num As bigfloat_struct ) As Long
   Dim As Long ex, j, k, c
   Dim As Ulong m
   
   ex=(num.exponent And &h7FFFFFFF)-BIAS
   If ex<1 Then
      Return 0
   End If
   If ex>=(NUM_BITS) Then
      'Print "error in function fpfix_is_odd"
      Return -1
   End If
   k=ex\32
   j=ex Mod 32
   m=num.mantissa[k]
   m=shr32(m, (32-j)-3, c)
   Return m And 1
End Function

Function pi_brent_salamin (ByVal digits As ULong = NUM_DWORDS*9.63) As BigFloat_struct
    If digits > NUM_DWORDS*9.63 Then digits = NUM_DWORDS*9.63
   
    Dim As Long limit
    Dim As bigfloat_struct c0, c1, c2, c05
    Dim As bigfloat_struct a, b, sum
    Dim As bigfloat_struct ak, bk, ck
    Dim As bigfloat_struct ab, asq
    Dim As bigfloat_struct pow2, tmp, eps
    
   eps.exponent=-(digits*3.3)+BIAS+1
   eps.mantissa[0]=&h10000000ul   
    limit = (-digits) + BIAS + 1

    c0=si2fp(0, digits): ak = c0: bk = c0: ab = c0: asq = c0
    c1=si2fp(1, digits): a = c1: ck = c1: pow2 = c1
    c2=si2fp(2, digits): b = c2
    c05=ui2fp(1) : c05=fpdiv_si(c05, 2)
    sum = c05

    b=fpsqr(b, digits)
    b=fpdiv(c1, b, digits)

    While fpcmp(ck, eps) > 0
        ak=fpadd(a, b)
        ak=fpmul(c05, ak)
        ab=fpmul(a, b)
        bk=fpsqr(ab)
        asq=fpmul(ak, ak)
        ck=fpsub(asq, ab)
        pow2=fpmul_si(pow2, 2)
        tmp=fpmul(pow2, ck)
        sum=fpsub(sum, tmp)
        a = ak: b = bk
    Wend

    tmp=fpdiv(asq, sum)
    tmp=fpmul_si(tmp, 2)
    Return tmp
End Function

Dim Shared As BigFloat pi_bf, pi2_bf, pi_bf_half, pi_bf_quarter, exp1_bf

BigFloat_exp1_bf_data:
Data &h15BF0A8B, &h14576953, &h55FB8AC4, &h04E7A79E, &h3B1738B0, &h79C5A6D2
Data &hB53C26C8, &h228C867F, &h799273B9, &hC49367DF, &h2FA5FC6C, &h6C618EBB
Data &h1ED03640, &h55D88C2F, &h5A7BE3DA, &hBABFACAC, &h24867EA3, &hEBE0CDDA
Data &h10AC6CAA, &hA7BDA35E, &h76AAE26B, &hCFEAF926, &hB309E18E, &h1C1CD16E
Data &hFC54D13B, &h5E7DFD0E, &h43BE2B14, &h26D5BCE6, &hA6159949, &hE9074F2F
Data &h57815630, &h56649F6C, &h3A211529, &h76591C7F, &h772D5B56, &hEC1AFE8D
Data &h03A9E854, &h7BC729BE, &h95CADDBC, &hEC6E5763, &h2160F4F9, &h1DC14DAE
Data &h13C05F9C, &h39BEFC5D, &h98068099, &hA50685EC, &h322E5FD3, &h9D30B07F
Data &hF1C9E246, &h5DDE5030, &h787FC763, &h698DF5AE, &h6776BF97, &h85D84400
Data &hB8B1DE30, &h6FA2D076, &h58DE6944, &hD8365DFF, &h510D6847, &h0C23F9FB
Data &h9BC6AB67, &h6CA3206B, &h77869E9B, &hDF338047, &h0C368DF9, &h3ADCD920
Data &hEF5B23A4, &hD23EFEFD, &hCB31961F, &h5830DB23, &h95DFC261, &h30A2724E
Data &h16826192, &h77886F28, &h9E9FA88A, &h5C5AE9BA, &h6C9E5C43, &hCE3EA97F
Data &hEB95D055, &h7393BED3, &hDD0DA578, &hA446C741, &hB578A432, &hF361BD5B
Data &h43B7F348, &h5AB88909, &hC1579A0D, &h7F4A7BBD, &hE783641D, &hC7FAB3AF
Data &h84BC83A5, &h6CD3C3DE, &h2DCDEA58, &h62C9BE9F, &h6F261D3C, &h9CB10AF6
Data &hD58FABE8, &h5AD3EDA3, &h0EEC79E3, &hAAA06800, &h90FEAB74, &hAFC6398F
Data &h4E26B910, &hDDF68631, &h5DAD43C0, &h25B3CD06, &h5520EC01, &h52302618
Data &h8DB8EF1F, &h2E35A007, &h01253334, &h6679716F, &h4343B727, &hAE280007
Data &h8549D9D5, &h3F31A159, &h81505239, &hB9D92FB9, &hF1D936AB, &h4FF1148D
Data &h69B6B50A, &h3E88305C, &h38D1400F, &hCBC1BB20, &h417FAC96, &hC8A06D8F
Data &h49CCEFA5, &h870A6547, &h44774888, &h595EA7D4, &hC7768A86, &h536EC499
Data &h122F7BAC, &h96381FA9, &h9671D186, &h698E0387, &h59B5A0CA, &hFF99FD8E
Data &h3363EB87, &hC9C8C083, &hE71028FF, &h699FB68E, &hF4A48E3E, &hF5352D22
Data &h170AA645, &hDB6C681B, &h1401DE12, &h46A0A23C, &h6157D83F, &hFF3C744D
Data &hCFF653F1, &h83060478, &h6B0FC71B, &h400EFB36, &h8EC7C9C9, &h72965778
Data &h3298CCA3, &hCEF95F32, &h5DD55804, &h6545037E, &hD674E738, &h244C22D0
Data &h415D1B6B, &h08F4CF97, &hDF392123, &h68C5AA71, &h9AE5606E, &h8D5CEFEB
Data &hCC452586, &h22AC5508, &hCA0BB905, &hB70A8671, &h5C93EA46, &hB92B7222
Data &hF199E5BA, &hB959DE80, &h7D93A302, &h18C4E560, &h8B676E3F, &h3B8D701A
Data &hC7FBA951, &hD35B63CD, &h2C54D2A4, &hDA862C38, &h3483AAE1, &hAF271B5A
Data &h9481C653, &h99FE8D55, &h46D5A009, &h9EC01907, &h03C84B46, &h3B2A35CC
Data &h9FB647F9, &hD92A13A8, &h6D0FFD6D, &h3DBA398B, &hC1719877, &hBEC9621D
Data &hF0D6C628, &h54757105, &h2AAB65EE, &h8F9264CC, &hB96581E3, &h98037AE0
Data &h45271107, &h3A55E0BC, &h8A8A0958, &hF16EB050, &h4508D817, &h46B86BEB
Data &h8B22C198, &h08DFB04A, &h2A83F8D1, &h9390D604, &h576E1330, &hED48C1CE
Data &h8A351526, &h212E07FD, &hC3842FCD, &h8704DCA5, &h8A354D23, &hC1C8479F
Data &h933D3C62, &hCA18242F, &h6C4902D9, &hB5B352BF, &h3AB70032, &h911B3814
Data &h143FC60E, &hB4AEFC46, &h307F03A9, &h47E5F48A, &hE3DF919C, &h175149FD
Data &h16D0ABBF, &hCE5614CD, &hDBDA5F75, &h7F7CB146, &h1F5F57C3, &h8BAE350F
Data &hC5EE83DF, &h183FD0DF, &hD4D77FBC, &hA60CEFE1, &hB2FA23A9, &h3EF50887
Data &hA1045CA0, &hD53E8C29, &hC023C552, &h9071FF11, &h9AD19176, &hF8A3DDED
Data &hA93D5156, &h9E587BEB, &h769C0E6B, &h561AD0E9, &h25FC4DBA, &h80CB02D7
Data &h74EFD5D2, &hE7E76819, &hDD108150, &h5EDF1DA4, &hEB9397C4, &hF04E8047
Data &h2EADECC9, &h1C9B1430, &hF5A1314B, &hE2C209CB, &hA8AA39E7, &h951EB6F2
Data &hC625D8DC, &h8D6CBD5F, &h81474B32, &hED276740, &h6EE09F06, &hFA19176D
Data &h07E9C4D8, &hBAF46886, &h84629185, &h35ABB64A, &h7E295A73, &hA5971A10
Data &h74816417, &h73D75C02, &hE175BB28, &hBF55FFDC, &h3BB9BC61, &hC03648E8
Data &h3F884EB3, &hA93E0C2B, &h41A240AA, &h6B490B08, &h3AADF798, &h5C013F2F
Data &h458272C9, &h7459751A, &hA5130F55, &hDA428B23, &h96A34D33, &h4127926A
Data &h258AE70A, &h17E5B298, &h3F90E6D5, &hDEB42C66, &h3D71E770, &h357325F6
Data &hC8D02097, &h3799DD02, &h7D5ABDC7, &h290B2E54, &h0E863E88, &hC1C2EB69
Data &h18523F0F, &h45A9D786, &hCD3D5612, &h93DA3620, &h13C20D51, &hC2D20636
Data &h28BD7C76, &h9347A34C, &hC86B6D71, &h5B47B17E, &hEDB7981D, &h3ACC5F46
Data &hADB8D1D4, &h01B8963F, &h35D8DE5E, &h0643DF52, &hD4771F47, &h0F47375D
Data &h4CE023ED, &hAFB709B9, &h3CB6E131, &hA72B2A96, &hC062FDD7, &hC1354E1E
Data &hE160CF4C, &hB4F13B2D, &hFC40F754, &h5FB38280, &hFB51CE64, &hAF29AC88
Data &hBFCFF605, &h6FDBDCAC, &hA94DE963, &hDF2EDB2B, &h83E26526, &hF4348497
Data &h8014ECF1, &hA9237A4A, &h9D3F03AF, &h28C04347, &hD2DEB051, &h9459FF52
Data &h984268BA, &h64EF4647, &hB50CBEB3, &h1ACDB4D1, &h149692F8, &h978D9911
Data &hC95881AD, &h40AC5087, &hCAB07F8C, &h93F134DF, &h95370B22, &h52B21E53
Data &h8597B30F, &h151E509A, &h728AF40E, &h316894DD, &h1DB6B367, &h1DD6CAA1
Data &hB60AFE73, &h7666A955, &h6938823E, &hF7AAD842, &h19AA48FC, &h32CC8623
Data &h8B3308D7, &h6EE6E25C, &h03D08DF0, &h426C2D87, &h7D405E98, &hF85010F2
Data &h2C012C16, &h8FB02D8D, &h71F193A5, &h72129AED, &h13A7BFF6, &hBE2D1C34
Data &hE66DE52C, &h62A6E924, &hC352C9F8, &hC5DC6211, &h48F3CB26, &h4C9E8A65
Data &hD61B1D40, &h0D10246A, &h71E37C76, &h7D3AFE66, &h804D324D, &h7AF61062
Data &h6BF6BC21, &hBDA35B55, &h7ADCEDA5, &h6FA0167B, &h2029808C, &h74C295F2
Data &h101F9165, &hDB46FF95, &hF9C53757, &h05B6873D, &hDFF26E9C, &hBEA1200F
Data &hB0A0CD8F, &h9C601C5E, &h925D6979, &h838E170A, &h2390FFB9, &h43329870
Data &hDE3FB6E4, &hFB10BF12, &hC2D61FFB, &hE47D8F43, &h4119EB16, &hF42F36FB
Data &h9DFE8E40, &hF22B3674, &hB1ACA811, &h61DC882B, &h2178394A, &h1CA20DE6
Data &hCC1F52F8, &hC70DE66A, &h7662B655, &hA1C86FB0, &hAAD90DEC, &h55BE3978
Data &h01B10DA6, &h8C01BD67, &h22376090, &h7290A68C, &h317582E3, &h5DABEF6B
Data &hC4D8ECC0, &hD18DCB51, &h9D9A9073, &hB322EE73, &h62A0F04C, &hADBD8AD6
Data &hC00463EB, &h5CE484AF, &h82B1F77F, &hD80EF362, &h7FED46DE, &hB21FE81F
Data &hFAE2E2E8, &h57DA3F19, &hDA0E64D8, &h0A6DA936, &h5727EAA0, &hAFAB9627
Data &h48C0993A, &h52542870, &hFB19A1C6, &h0A832D18, &h8A7F6E6E, &h7959B274
Data &h0E0AC56B, &h00C61130, &hB2903BF1, &h06258B52, &hF03D63C8, &h94BED0EB
Data &hF915C9DB, &hDDEAF825, &hE4953AC2, &hED6939E2, &h66F3DE3D, &hB3D9951C
Data &h1053CE3C, &h3AE8A2A2, &hE3688FA5, &h859A37D6, &hF4774F66, &h84F4706F
Data &h0DFB84F0, &hC2654849, &hB80C427B, &hB3E390B3, &hFF487E38, &h3C21CE0D
Data &hF2BCA5DE, &h62126DD5, &h60FA681F, &h60D9BE3E, &h89B624D3, &hB602D777
Data &h6B9DF23D, &h843872D2, &h888AE9A6, &h2EE5BA54, &h080EF95A, &hD57FCCF0
Data &h7839F5FB, &h18ED14F2, &hD8FBA442, &hBE0D3E0F, &hF57310A7, &hCF5BCCA9
Data &h07478A05, &hB624E118, &h833A093D, &hB448EF2A, &h7E8722F3, &h4A0B12C0
Data &h1E89361C, &hA8606DFB, &h95B14D4E, &h9537767A, &h6027A6F5, &hD6427FDC
Data &h29DC0C00, &hD9ECEDE8, &hC8E00247, &h9E0860DB, &hE01AFBCF, &h26B13895
Data &h4CCE2E35, &h367A3EAE, &h1C05D8EF, &hA926CF3B, &hFE3DDEFF, &h71F1F3BD
Data &h5AF22FB1, &h962FDD09, &hDEABD9E6, &h3387EFD0, &h585FB254, &hB0249575
Data &h50A5D8AB, &hFEA44C91, &hB464FE85, &h175FCA27, &h059CB0A6, &hE5FA29D7
Data &hCBAE759E, &hD283E5DA, &h04184103, &hAE480339, &h7790A582, &hE33A3871
Data &hC7D98BB5, &h70CD2E0A, &hFDD379C2, &hB49D5024, &h26CB98F2, &h6925BA30
Data &h34960742, &h0C1D1A39, &h0D8BE2C7, &h9C0CE6FD, &h8F004757, &hE76AFCEA
Data &h9DBBC6D3, &h8B0A1C52, &hEEC259B0, &h7837860A, &h154E8573, &hF8A8D44E
Data &hEBB83128, &hC2FACE49, &hBAC6C395, &h01D6B4B7, &h04697F18, &h680C430E
Data &h8D64E645, &h3384CB99, &h24825E44, &h3991DD4A, &hE46E825C, &hDF1893B4
Data &hD18F38F4, &hC4519DE8, &hE4778125, &h1CC1F422, &hEF7E5780, &h1D34446E
Data &hF1311C22, &hFAC35FA6, &hE447A08B, &hABF43940, &h62A0EC06, &h88075A23
Data &h61B7DEA6, &h5506EF7B, &h4657755D, &h991432C2, &hBECED2E6, &hC4066522
Data &h43C52165, &hCF28F8CF, &hEAA85D51, &h4B31880F, &h94E89226, &h5FDB6640
Data &h0F9F7AB3, &h721FC635, &hB7FAFB26, &h1F4A61DB, &hACF8128B, &h12F7837C
Data &h57F80241, &hBBDE631C, &h1967C667, &h53A0AC04, &h82B9DC44, &hAA4CE585
Data &h36A66342, &h3ADB8883, &hA52AFE9B, &h125035A1, &hD556E627, &h9B55A121
Data &h666F79B7, &hF23E62B4, &h1274E594, &h18F70F1E, &h4B1C5C6F, &hFD9BD07E
Data &h94C26971, &h619E9BC5, &h4CE07E87, &hDF9DB221, &h8D6EAAAD, &hF37148FC
Data &hDFBA9D08, &h1AAB03B7, &hB365D0E1, &hDE6E2B31, &h7B1CE113, &hEA569F2E
Data &h88E2AB0D, &h85581322, &h40CCC847, &hE3301414, &hECC5C12C, &h35823C81
Data &hFB24ACDB, &hF569A4CA, &hA05A5B38, &hE636EA77, &hD7724752, &hEB15B585
Data &h0DACAA8A, &h0E3AAF8D, &h023026A1, &h9593CCDA, &h77A37422, &h96C44234
Data &h912220B7, &hDB698D42, &h1D66FA67, &hBD0F6E07, &hA96E5C70, &hCFF9647C
Data &h97201CBB, &h2F494FC2, &hAC7EAA77, &h468A89EA, &hF53F60FB, &hF4095BFB
Data &h99C3D03B, &hA6285E9E, &h76EE2889, &hB850C1C0, &hD7433FC2, &h5B79CB77
Data &h528B22A5, &h75F725D8, &h0697E088, &h6224DC4C, &h8EB1D6D6, &hF4AA402F
Data &h844F8975, &h8A3BEA92, &hDC1B9D9A, &h1A61F5AB, &h5BD1788C, &h7EE6600A
Data &h4206DF72, &h1DF64D45, &h1A3A3EF5, &hD004EF49, &h6AB4E016, &h6B963173
Data &h89A9F254, &h84C7A39D, &h712194A5, &hDF8CDA94, &h2CA7DCE6, &h3D5DF24D
Data &h669DF411, &hFC19757C, &h79F3208E, &hBF6C1CC7, &hE73C7300, &hF4367994
Data &h4C53CAEA, &h3DF898A4, &h10FC503A, &hB1084BC4, &hD7E118BF, &h1EF14967
Data &h5C7D3DC5, &h426B339E, &hC7A85FB9, &h920353DE, &h29DCECA8, &hC7A1DA3F
Data &h742451EE, &h656C7904, &h1E530B0C, &h86B2D279, &h5307A9E0, &h71D4B773
Data &h1A59AF0F, &h967D32C2, &h7622B5F5, &h00DA0779, &h9884546F, &hC46CCF24
Data &h3A6244C1, &h5741D2CA, &h3318D044, &h14109193, &hD552560C, &h0DBCAEF4
Data &h8FF33F97, &hDF6F6A28, &hAECF5685, &hF9EF6146, &h60F37563, &h07936660
Data &h60A83630, &h9B2FC798, &h192D1B16, &hEE95A2A8, &h0385BD1D, &hD93965AD
Data &hA34E7F1D, &h4114E19A, &h6B5366B8, &h11A159BD, &h76BF0387, &hA909C37A
Data &h376027D3, &h2D21BB5B, &h66C93B75, &hE6EBA4A1, &h7C5B9D43, &h8FE8089B
Data &h2A518FDC, &h61B3795B, &hE3BA040A, &h3EF421DC, &hBB082868, &h139117BD
Data &h60150BB6, &h8B63FC1F, &h6803569D, &h6DDD443D, &hCD837BB1, &h6D900CB7
Data &hD93B1CBF, &h103FFD1B, &hDA32DF75, &h221D3508, &h6B145486, &h74676C56
Data &h32EDDEBA, &h8563204F, &hA78629F0, &hA21C751C, &hF388EA46, &h5998390E
Data &h40781E8A, &hEBEA231B, &h9ED6A679, &hFC90B88C, &h6AA4D2C2, &hF228D9CE
Data &h2720C26E, &hF42FE375, &hF02F5640, &h73F1A472, &hA0540A23, &h4723878A
Data &h1F1662FD, &h6F93E796, &hEFCF40C1, &h24077284, &hFAB409DC, &h0EA2C8C0
Data &h869A26F3, &h086A9825, &hC247793A, &hD9DC70B0, &hF0A09C59, &hD17B92C8
Data &hA19D627A, &h0BAB0A3A, &h69FFB942, &h31DBA16D, &hD1B8D65D, &h9495813A
Data &hD6ADFC41, &h060C9420, &h2333BECD, &h534F7D3C, &hDA481273, &h25EC1F44
Data &h83E7E1F2, &h258688FB, &hA65F4CFC, &hD2493F9F, &h77BC4495, &hF97BABA5
Data &h856017DD, &h173F156C, &h4C70ACFF, &h0CA847E7, &hF8EF4584, &hF9E72AE6
Data &hD7232599, &hF5550F87, &h49AF6862, &h918DF1BB, &h0181EC0E, &h582D4F91
Data &h741EEB0E, &h20B82317, &hB11BA7E4, &hF5E5771D, &hE68A4971, &h5AEAF323
Data &h9FE0A408, &h24305C3B, &h6B428136, &hA9EA38A0, &hC6364A17, &h24654471
Data &h5D6DE297, &hD15FF973, &h85A9FD5D, &hE724CDD6, &h3EC4C63A, &h1CC075EB
Data &h69E2A731, &h4126DA4C, &h5252ADDE, &h1F0AB475, &h98C75669, &hFCBDC6FE
Data &h798A35A0, &h9AF1AA88, &h0F64A179, &h0F3D7D88, &hB9300F56, &h5EBAC096
Data &hD21150BC, &h951D226C, &h136754E7, &h1016354D, &hF8E96CEC, &h1C56A715
Data &h75C311A4, &hCBB8E4D5, &h09071B33, &hF9348B90, &h960DC278, &h43B2D965
Data &h5E5544C7, &hAF19B1A4, &h57AEA51A, &h7EAAFB8D, &h44D0D958, &h4A95DE45
Data &h8E8F7C35, &h0B1A55F9, &h51E1D493, &hDC18EF26, &hF7862845, &hBC4AA51E
Data &h2360DAA5, &h2231E180, &h93CE9587, &h3258BC75, &h4D4E7D2A, &hBE61CE54
Data &h9F1FF7E7, &hF032DF7E, &hA8652515, &hE9CDA8D9, &h5608B309, &h25038C78
Data &h64C66FAF, &h13C4E20D, &hD11F70AF, &hCC608ABF, &hF68B13F4, &hD084621D
Data &h2D745FDA, &h5E8EF1FF, &hABF1B8A1, &hCA3576C5, &hDCB48D88, &h73ABDD3A
Data &h817C72F5, &h9B85C774, &hC97560EB, &h4AAAA08E, &h685DC315, &hAC835478
Data &h576291B1, &hD406F80C, &h4183A17E, &h2D38DCF4, &hA938D9D9, &h5A9942DE
Data &hC4DB4B83, &h6E5A50C4, &h5EC2226D, &h331AC1FE, &hDC270CBC, &h7A2F97B0
Data &h3383B56F, &h3C775404, &hCB7F884A, &h554E1FB0, &h330AF671, &h53253268
Data &hFC83BEBE, &h79BAAACC, &hA0581EC1, &h45819BFD, &hCE74165E, &h4665E8AB
Data &h2CE52CCA, &h2D8219D6, &h64E18E60, &hD031271A, &hD85B5DBB, &hABE4025C
Data &hFD294968, &hA4314EC5, &hC5D54622, &hCD57E344, &h29F8945D, &hD708C88F
Data &h04632821, &hBF5F5307, &h6693B553, &hA732CAE9, &hE51B0FF2, &h0128B207
Data &hE3F41A65, &h42F968FC, &hA30756FC, &h73F495B8, &h72DD4770, &h7A4DDF2B
Data &h357DC101, &h4B87F424, &h969548CD, &h5C5ABB14, &hB3598402, &h0D2E5267
Data &h9EDC7B1D, &hDF96C01F, &h1C441452, &h4129CF0E, &h6195F930, &hCA664711
Data &hF31485E6, &hD62AB999, &h234E10B8, &hB4F5BF1E, &hAE2383CD, &h096CF1E3
Data &hA0FFFFD3, &h27917FB0, &h4DBE4A11, &h53FF746A, &h86EA7305, &h180933DE
Data &h63C0C10C, &h6A39AF42, &hC7FEA31C, &h95278273, &h6F2B6C3C, &hD11E2926
Data &hF787DC5F, &hF69C336F, &hEE59B39D, &h7FC2B13D, &h81AC2B6F, &hC78E06A2
Data &h7243E071, &hE5531F4C, &h48ACAE57, &h63062FC8, &h9AA753B1, &h38655E21
Data &hFF7B7EA2, &hED25B63B, &h58D10EF6, &h7CC8EB74, &h68982C45, &hF15E5333
Data &hC53E1D4A, &h59C2E0F0, &h96C8F720, &h77C6EF6C, &hD3189724, &h32801719
Data &h1ECE0EE8, &h364163AC, &hF40C3AA9, &h0D60D72C, &h0629E0D4, &h2F7224A8
Data &h40BC2C1E, &hA635DEB1, &hEFD50AF4, &hD6FA9573, &h357D36F7, &hAECD67A0
Data &h6D0C2061, &h23EB61DF, &h5BDC5202, &hEB9B2F69, &h4AEEABB0, &h5663DCE8
Data &hC596B508, &h4F35C2AC, &h30F586CF, &hC9B74148, &h55651311, &h79A9875F
Data &hF373963D, &hB9BD2B00, &hBBFB8350, &h71383214, &hF3D3A382, &h1CE10D53
Data &hC0DF25E6, &hBA8C5E41, &hB8DB74C6, &h9C82EDA1, &hBE2215C4, &hD337377A
Data &hF2DFD55A, &h1A74B40E, &h64A2DD15, &hE80056A1, &hBE02A3F2, &h7A1E0A43
Data &h2274F62D, &h53DD45B6, &h6941F981, &hC4728C16, &hF1476210, &h84CCB2DF
Data &h82715210, &hBED25D63, &h7C95B65A, &hB314791A, &h031A9039, &h2C72BDBE
Data &hFF30D7CB, &h40C7CEA9, &h752576D9, &h4F4F3883, &hAFFE613F, &hA1693829
Data &h480E00B7, &h2FFC44E8, &hEBA82EC9, &h272693F3, &hC5983EED, &hA31F9841
Data &hAA3ED13B, &h32DD5D01, &h7C56383D, &h463CD4A6, &h7525DF12, &h1624BFF5
Data &h08897993, &h8545E5B9, &hC22284DD, &hAE057048, &hA434EB8C, &hFEF7FEE1
Data &h1FEA03CC, &h3965D2D0, &h58DBB6C9, &hD5479FB9, &h3F6DCCDD, &h77F45573
Data &hFE8A8FA7, &hAB666F1D, &h53A8A3DC, &hAF7E35B9, &h543BC56E, &h97FE7F84
Data &h4DDA3828, &h111D7403, &h4E23C926, &hE49D3121, &h72932D2C, &h7942DFEE
Data &hED826907, &hC8012F0B, &hF56E1BA8, &hD414A96D, &h791F3361, &hAC9B1BE3
Data &h7CC192F1, &h0DF55C84, &h66E9CC7D, &hD3F27FEF, &h73BC6015, &hA30214A7
Data &h3B10F07F, &h21731EF2, &h3C5D2754, &hBF508E4D, &hAD66B06D, &h868B996B
Data &hF19BF607, &hA62A46D0, &hE89D24C9, &h572579C9, &h823FEAC6, &h3D0A6BF4
Data &h74A5978E, &h4377F61A, &hF53A386B, &h103880DF, &hC767054A, &hBF1450A6
Data &h3CFFCD34, &h19A0AF52, &h89CC4068, &h7248EC04, &hA2D96A74, &hA34FD1F4
Data &hBB3FCAA1, &h9A777C79, &h2ADFF7DB, &hD1DA3800, &h0A5FBD50, &h85822958
Data &hAA2B10CE, &h60138B4F, &h364D2029, &hFADA8B9D, &h40C9DBDD, &h74F892CD
Data &h4E7BBB8B, &hEBA0E427, &h6802B2E3, &h56D58CF4, &hDD886C4C, &hCE1E5C16
Data &hE528F460, &h9E7390BF, &h80798148, &h7C158738, &h956EEB7E, &hB8133390
Data &h613F0C33, &hA36DD50D, &hC560AC2D, &h44C97199, &h1012D675, &h93D156F6
Data &hAE4156A8, &hB62C7055, &h1CFE6EA2, &hD1519A75, &h82695A72, &h2DB5791D
Data &hC0EA65DB, &hCEEFC710, &h929DE632, &h7F3E374D, &h3DF06C44, &hA03F519A
Data &h5AA0BFFE, &h9D8E15B6, &h382EBB5A, &h2CBCA121, &hFF1519BD, &h4363EEAF
Data &hE50B5B50, &hEC4F0AE8, &h26D93F3A, &h04050AB8, &h34876CAF, &h31E76301
Data &hAC076B96, &h72B7D152, &h5B041D12, &hEBABEE9B, &h49F9AC15, &hB509EE1E
Data &hEA198868, &h6F2FEA52, &h0CE52701, &h3AE2FB73, &h1E952DBA, &hC98887EC
Data &h4A76FC6A, &h06A51FC2, &hA49B8173, &hF81EEE71, &h8238B825, &h17F20C8E
Data &hA4EEA244, &h23CA7E0F, &h40F2441C, &h501BBF66, &h6C636CE8, &h726BE88A
Data &h9631F820, &h46899DB4, &hC89BD589, &hFFFA5ECE, &hD6CC2882, &hFB18C37F
Data &h91EBF305, &h3CCC03E4, &hE812C005, &h873D40E4, &h5180E551, &hB784D77C
Data &hD4F2073B, &hE0A7476F, &hB4599AAD, &hD8FCE797, &hF1AD2C41, &h162B6EEB
Data &h8913E7AE, &hE77742A5, &h4348CABB, &h3C2AB9CB, &h13C4B4A0, &hB3491816
Data &h6D4022A1, &h942FDC27, &hEBCA724E, &h525D5835, &hFC837E78, &h14C4D2EB
Data &h70D7FBFB, &h41D0CB19, &h85105387, &hB5391A49, &hDE014278, &hC9F8C9E2
Data &hD97D27A8, &h2686D4AE, &h6349DF6D, &hB6965ED9, &h79231CC8, &h093FBFE7
Data &h9E802D5D, &h1E53C93F, &hCA0D8281, &h9C295C7E, &h27471261, &h90D93571
Data &hA3AE3433, &hF70B62B6, &hCCF69073, &h3D044087, &h044E20B4, &h61E597BF
Data &h40B55D89, &h3E632089, &hA6B263A2, &h4005346B, &hD76E4451, &h46EF9E0E
Data &h69EB29AE, &hAD5783C4, &h9A75C562, &hFD157B71, &h33127C95, &hBC821A16
Data &h5B0EA055, &hAE0E394B, &h38F2DF77, &hCD6BF3AC, &h345AAA6A, &h0C56821E
Data &hE5911668, &hF1B1513E, &hB1D95FA2, &hCF09BBB1, &hEADEF7E2, &hF3D76933
Data &hC6B1E5D6, &h690D2375, &h14FA874A, &hEF100EC4, &hB5114A8E, &h83E849A8
Data &hBBC21443, &hBA109634, &h3BACF5BC, &hAED5FC16, &h71EBE2AF, &h69C59E19
Data &hB7754FB8, &hC5B0B350, &h591A6581, &hD956ECF1, &h6B49FFCB, &hBEDEE98E
Data &hC1FD4BDD, &h6E385E78, &h86A77A58, &hB43A7222, &h08A866B1, &h8156ACAF
Data &h01301D4F, &h593DD42C, &h17B65FBD, &h368319CB, &hC0D9E46C, &h49227877
Data &h7C77BBF7, &h93FCE658, &h28C4EFA8, &h909BF51E, &h9F902501, &h11E328CE
Data &h03F42BAA, &h7F6AEA3C, &h85CCFE09, &hB3EF0052, &hC3140BAE, &hFEEBC29F
Data &h41923BF1, &h89CEE62E, &h3F954E82, &hB22435B1, &hFBEDDFB1, &h01256398
Data &h3F232855, &h05800877, &h9C04F05A, &hA9D39D8E, &h33E1E4BE, &hAA062982
Data &hB45548F3, &hE9B7BFCC, &hF97AEBC3, &hE03D6F7B, &h169C738B, &h48E3F433
Data &hF5D303E6, &h29AB2173, &h8ED7EF19, &hD72C00F4, &h88604E4A, &h18668A8A
Data &h5637C565, &h8F4BCB37, &h72FBE27B, &h63BD3A9F, &h97B258AA, &h880A070F
Data &hD8FFA141, &hD7A35C39, &h97CFA2BA, &h1DBB2A36, &h0783D768, &hB06D5D49
Data &h1F518A1E, &hB677C93E, &h2062A75F, &hCC8BE229, &h2B2B139B, &h4CBE6D1C
Data &hB79DAFA4, &hCDDFCA37, &hF7BAB7EC, &hF99AB4BF, &hE5C015B3, &hCD964006
Data &h400C0D6A, &hA3A87A6E, &h0B4CC55F, &h617B3CB1, &h65863E12, &hBA0666B0
Data &hB8DB4CD8, &h66A52951, &h3AD70678, &hCCBEC495, &hB8AD0B9D, &h3DC655CB
Data &h5BCF248D, &h852C5073, &h19116016, &h811FA74C, &h715DE1DE, &hD64D32DF
Data &h234D93FD, &h3AB9BD3B, &h9A278221, &h710AF63A, &hFD9043A8, &hFDF74194
Data &hD3FD78C5, &h982C1078, &hCFEC1E67, &hFF0DA7CD, &h2B8C76B2, &hD3C4B9E2
Data &h05DB5178, &h936F5707, &hB304DCBE, &hE27D840A, &h8B1AB537, &h0B281A4F
Data &h90E32ADA, &hEDE709A4, &h4526CD78, &h1682D116, &h98652F1B, &hD94DCB11
Data &h9A1F8FA1, &h4D05FF4C, &h60C99744, &h95CED7BD, &hF717CC03, &h240F2DEC
Data &h12AFC406, &hA0226B06, &h04B0A76F, &h36077C8E, &hAEB492EC, &h4AF8C144
Data &hC04A3FF4, &hCDC04CA3, &hCFB7B859, &h7423579E, &h6B519E3D, &hED805AFB
Data &h72C3B728, &h4319EF47, &h68A9C81D, &hD90199CF, &h7193DCAD, &h1E3F00F4
Data &hEA1A90CA, &hF26390A9, &hA7AD983A, &hC02304D0, &h92FB6F64, &hBD6452AE
Data &hE3911578, &hCACAD461, &h05D0D0AD, &hCAF8FBA8, &hC17DD260, &h111FC6E4
Data &h00C3EF86, &h585FC075, &h623FDFD3, &h74CE6B56, &h3709458B, &h77BFA38A
Data &hAFA9240B, &h1ABAE8A0, &h789D667B, &hCF2A4373, &hBA6C26E3, &h4B469DDF
Data &h6BDBED16, &h8CA17A7B, &hB24F74B5, &h7861D35C, &h63A51B02, &hE4A68592
Data &h01646AC9, &h87EC3DFB, &hE58D70B1, &h6BEE9552, &h3C9E0618, &h8ED2EB0A
Data &h11B0FA9C, &hF8844AB0, &hDFDA39F8, &h67835A6A, &h596F0BA2, &h0A22CEE6
Data &h387E9219, &hC5E7ADE2, &h894C11D5, &h72F19920, &h368B9E6F, &h7C1C5BD9
Data &hC47A1F90, &hBDCAF59C, &hCF5EBAE0, &h20803228, &h72637E79, &h7C019D0D
Data &h0ABBA209, &hFE2F0A25, &h839AC771, &hB93951D9, &h016EEA01, &h8CD5FA84
Data &h5DC8FDEA, &h3DFE3713, &hD925F278, &hDACF0DEA, &hD1546804, &h7DCFEE83
Data &h462B21E2, &hBFF23C7A, &hBA39FA78, &hB3267EC3, &h0AA447FA, &hE6CCF1E8
Data &h5334F51F, &h90CD47F3, &h4700C920, &h4BA9EDAF, &hCE59B4A1, &h23869AC4
Data &hCCDA998D, &hE534CCC3, &h029FA45C, &h0A85FA66, &h243AB3FF, &h1012115F
Data &h2AC596AB, &h5AEE7DD0, &h40FDF44C, &hF2D73D59, &h200ECE71, &h33AA949A
Data &hA140AAFB, &h296AC430, &hE991CCF9, &hE165D4FC, &hA1690397, &hF71D9AD8
Data &h53D36974, &h1155320E, &h9F974820, &hEABCBB2C, &hFECDCFD5, &hF3317337
Data &h1ABB961E, &hCBE6C782, &h9F14C529, &hF99D9571, &hDA7EB236, &h181BC26C
Data &h0478795D, &h42CF32F8, &h03AD3C47, &hDF8FE72C, &hFD75D20E, &h28DC1603
Data &hBEB07AD0, &hEE80EDD4, &h7085FDC7, &h154C780B, &h72772951, &h4AAF4E6D
Data &h9D56606D, &h1986EDC0, &h1B64269B, &hF9E0A539, &h33FE1505, &hF8940977
Data &h77E7E171, &h47D8BF4C, &hABB6F185, &h3B94D515, &hAC81A7A3, &h2C5A7D8A
Data &h59BD02D5, &h3CBE9678, &hC224329D, &hA2EC9812, &h0E2FB66B, &h2983DAB2
Data &hE48D7983, &h54D9FF76, &h884DF42B, &hF59464C4, &hBE9EE773, &h3DBE5C4D
Data &hDABEE149, &h7F69EEBA, &h60C91926, &hBAFF65EF, &h134AE068, &h505E043B
Data &h94479D60, &h980A1A6A, &h6EF9B76C, &hED8969A6, &hFC58D1ED, &h6DB46D46
Data &hB4397FFC, &h26974B02, &hF37B3BDC, &h1A9BFEF6, &hF01B0FCB, &hA0E87F4E
Data &h6686A7BD, &h32B10D95, &h20FA24AA, &h622A5F25, &hA3CEABC1, &hA4D7118F
Data &h4430148E, &hE07DF49D, &hA64A0872, &hFE93C760, &hD45AF82B, &h1A2F4E68
Data &h7E505C29, &h2B3A68C6, &h19C6E034, &h4DE3013B, &h05F9A472, &hAEFFF172
Data &hB07C36F1, &hDF181F3B, &hE79BB3D7, &h9B0E5AE3, &hA87CCBE6, &h8636E1CA
Data &h1179B61B, &h5A43163F, &h168EEA43, &hCE982CD1, &h8646F71F, &h5258155A
Data &h19C9F59F, &h61B16497, &h4D346079, &h1CEACF18, &h644F524D, &hBC161663
Data &h6D541E2F, &h1D231E8F, &h3268E1B9, &hE45B3078, &h6E3356D8, &h6A43697B
Data &h5C2AAE04, &h9C950E5A, &h52193498, &h3C540E23, &hEB88DAA7, &hFCE3779E
Data &h56C9B0D3, &h351534EC, &hF729E636, &h1399F7E3, &hE3F33E00, &h12ECF5B1
Data &hB41E3F0C, &h1FAB620F, &hB6A0E4BD, &hBC3ED193, &h3A9EE5AA, &h78DE1A73
Data &h9327C19D, &h4E49EF8D, &hF1D82A86, &hF1477E89, &h42AC416E, &h08496EAC
Data &hC59AE687, &h9A924DCF, &h3524C398, &hCA70BB3A, &h4C3634D5, &h86B5E36E
Data &h22A53925, &hCC1C6079, &h6DDC7C24, &h6FBFF329, &hEED8DF5C, &h571F99EE
Data &h3E984D72, &hCD3805ED, &hF2DC0406, &h95F6C9DB, &h7821F9FD, &h8BE66040
Data &hCBE943BB, &hF8BC3E83, &h218A3A9C, &h293584C1, &h6A584E14, &h3A5EB830
Data &h3E2BF903, &h8FC67DA1, &hBFFEA5FC, &hC4F95B9F, &h1D50CE00, &h9A2BE590
Data &h4A467CE4, &h82E90B23, &hE5C691A2, &h3E8489A0, &h5E4DD64F, &h13C4293B
Data &hA9FB9303, &h2A286652, &hFD77F1C8, &hC4794B7C, &h64F563AC, &hF87750E1
Data &hD3B2094F, &hDCF0D406, &h2E2A6F86, &h64258D12, &h31685D49, &hE5FDABB2
Data &h68EF2E90, &h8E8CE43E, &hA34C54CA, &hAD88B559, &h3C86BF10, &hE7361BC7
Data &hF5DA77C1, &h17ECFCE2, &hA1125D6F, &hC50DB78A, &hA7533A30, &h37124C14
Data &h616CB8FD, &hBE2BDBEB, &h6A3F9F15, &h0896551F, &h473CD608, &hFA44972D
Data &h665A705E, &hA1FA4052, &hF229F481, &hAD948D17, &h2E184422, &h7C1599B0
Data &h7EEC7CED, &h6C41A839, &h9761C2BA, &h969C43BA, &hCA6A1423, &h880490E8
Data &h740EFE2F, &hFB6E5963, &h8413E728, &hE37779BE, &hC12B74AD, &h9266295A
Data &h8EA8DCA3, &h51E64391, &h28954CA5, &hFC43DDA4, &hED643F20, &h3BE424E0
Data &hE0926198, &h6E83D25D, &h8C621A2A, &h17A50731, &hBF328793, &h73E96B64
Data &h3BDA707C, &h1BADDED4, &h2B2EF599, &hBCEF842D, &h45894BF3, &h7EB2DBD3
Data &h1D79D086, &h0C5A83D1, &h5D9F1472, &hE7FCA351, &h846538A0, &hCEAD538A
Data &hD4BE881C, &hC0228969, &hD7EDFABB, &h93742061, &hBBD90B3B, &h5124C9BA
Data &hBF472010, &hDC031E87, &h2754A96E, &hEFABBB89, &h09913A88, &h476221CF
Data &h59C099D2, &h7C371549, &hB7D9E040, &h57F95EA5, &h89A7F954, &h6F52E18B
Data &h7AFCB004, &h10771A31, &h2CA41FFD, &hFA6B5D9D, &h23B08E48, &hA7B71C18
Data &h13CB7903, &h8394B4F5, &hC3E9A52A, &hFBBC0552, &h858180FE, &h1695019C
Data &h0E47FCDC, &h19AB401C, &h10717517, &hD6631450, &hC3916775, &h899D0F3C
Data &h7948F5A9, &h55311F32, &h9CE5DCEB, &h5564F2B7, &h0A5D2127, &h0C92EDC5
Data &h7943E252, &h48632B2B, &h2F160153, &h54018428, &h33A0A5E1, &h5520F69A
Data &hAB335A28, &hC4C61A0B, &h51028CA5, &h32E3823A, &hDA49915F, &hCE46C955
Data &h41093586, &h3B0ED66F, &h041B34AF, &h51855540, &h2F82FAF5, &h4A95CF9E
Data &h45342096, &hB35562B2, &hBE2FF23D, &h7697278E, &h59B5A25B, &h657B5712
Data &h7CF9863C, &h8708484D, &h2BC34A3D, &h69617E16, &h9109DA82, &h8293DA45
Data &h3D98EDF1, &h259A82A3, &h21ECE87F, &hACAA81DA, &hF029996A, &hE982AF37
Data &hC28372DD, &h3EB5FF23, &h65584A2A, &hB37761DD, &hA36C2FE6, &h9E77BCD5
Data &h94A95AAF, &hC1E2B70C, &hA51D1D08, &h9AE4CE07, &hCD3BC079, &h00A05D63
Data &hF91792E2, &h6DF92070, &hFE5C41FE, &hF600F211, &h7D11B12F, &h1A072C54
Data &hC9DEDF7C, &h720CD6FC, &h32F94439, &h80B2F794, &hAE0ADCA8, &hD76AC198
Data &h424D079F, &hC403F117, &h37DDA345, &h70892359, &h4205A96B, &hB9D96AB8
Data &hF09A3C95, &h2C4E883C, &hC91B9C8D, &h9A8E1AC2, &h4C916C4A, &hEFD526BD
Data &hB342B309, &h5ED298D7, &h384ED769, &h7CA0FE6A, &h5F737240, &h2E3161B3
Data &h72EBE9C7, &h5C447247, &hD200A236, &hC6CBB38D, &h803CC959, &hDB89791D
Data &hE956A6BD, &h6A80993C, &h8F97CA23, &hFA9899D6, &h064C8E3C, &hA5273794
Data &h94EAAB97, &hDFA367B3, &h966B9F5A, &hA5823D86, &hA1623F18, &hAE6504AC
Data &hBF90C5EE, &hEE1C4521, &h6FDBB4E9, &h483E8287, &h4AF2B9D5, &h4AE88C15
Data &h248778C8, &h176320E3, &hE67E067A, &hCFF4DE35, &h247473A7, &hB844C8F0
Data &hE3FAE77E, &h4CD39CF5, &hE6ECAC75, &hBB1F4068, &hEDB7E714, &h4B7A63CB
Data &h28AB7131, &hC65B1477, &h8CC1ED4C, &hA9A774D3, &hE1DECDAD, &h81AA9049
Data &hBD790E67, &h3635A3C1, &h6C9AF301, &hB51BA751, &h4B5844EE, &h2539FF86
Data &hD455DCF6, &h8C8930AD, &hE2F063D9, &h829D0889, &h50F9BD10, &h3C3F1981
Data &hCAED1805, &h07625F52, &hEBCFA918, &h5D1D3C37, &hA92A1216, &h265B5F92
Data &hFC5EC51C, &hA4B0BDDA, &h43DBB0BA, &h2889E85D, &h8C39A5F7, &h6FC9CAEB
Data &h37B4342C, &h77C1FA7B, &hBCC27285, &hEA6F23A3, &h56B9FCC0, &h0859B713
Data &h2F815001, &hC6A2F762, &h8AFEA1AD, &h88CC9ACC, &hFA8036D8, &h2CBADC71
Data &hED197060, &hA7A61193, &h6C40121F, &h2027704E, &hEA584BDB, &hA3FE8D57
Data &h73642FA5, &h574A05CC, &h84A8F8C3, &h49B81D17, &h58391C5B, &h09E440DB
Data &hBE61C28B, &h947F19A9, &h0049B32F, &h39F2E10F, &hFFDAC457, &h3A525B4E
Data &h899AA89C, &h84C061FB, &h75D1B1F4, &h0C12B2A1, &h93D39EAF, &hDABF4AD5
Data &h20AA1D4B, &hCBED3D59, &h6939BB57, &hA810F356, &hCC99C975, &hC86AAEF1
Data &h51648FFE, &h7E2355C4, &h015E4050, &h675EF326, &hE535D3FF, &hC8654556
Data &h91653EAE, &h2EA80EB3, &h63E1CCFB, &h95C665A3, &hD7045C0A, &h8A56D864
Data &h0488A24F, &h2294494D, &h7AEC1E48, &h81045352, &h84095C7B, &hE9B287FE
Data &hA475BF06, &hD68CB917, &hE79DC6D4, &h07BA99D2, &h02BE65BB, &hEC73BD6A
Data &hFA750113, &h20040E34, &h10F1F8B1, &hE373C20D, &h6D871282, &h3335034C
Data &h0D451DCB, &h8878C7F3, &h5C9D52B2, &h4776B47C, &hE72FC116, &hBF758342
Data &h507BC7BF, &h90FFA877, &h3A0371B4, &h06FF6741, &hAA8E1B76, &h6AF7AAA6
Data &hE24752FB, &hD176CD7F, &h17AD3AB6, &h44265871, &h20C3F33E, &h56C4B2A4
Data &h0ABE21BE, &hED5ADE0B, &h31C81566, &h4EA5D299, &h7E265F25, &h4AF719FC
Data &h473689F3, &hDDF77089, &h3F6D8CFF, &h85BEFE09, &h239C9D1B, &h4F82A1EB
Data &hEFB08EFD, &hAD1313AF, &hAA5BD41B, &hD39CC86C, &h9ADBBD00, &hD11F756F
Data &h8151630E, &h33A34C8E, &h633A4AFA, &h7FCA0583, &h0B7B8D95, &hD3FE5A48
Data &h76002F12, &h2497463A, &hC84AD1C3, &hEC418EA8, &h101C8557, &h2EAB8BDE
Data &hBD0F6E81, &hE9CE1CF0, &hA21EFA6E, &hE634DA07, &h7CB9AA05, &h30CD7E5D
Data &hE4180E7F, &h90897154, &hBA5ACF2E, &hC9E5684A, &hD6745792, &h1AEAD1F0
Data &h4CBBCBFD, &h3586B42A, &hABCC58CA, &h8ACAE697, &hEDE8C6D9, &hDBCBC3A6
Data &hD50EA1CA, &h61AF8284, &h437A76F0, &h3072F180, &hEE4242C5, &hC1C76A37
Data &h2F4AC272, &h91D80A7F, &h384FE347, &hC6E713DC, &h845C25A4, &h61713EC0
Data &h617CEFC0, &h8BE81BC5, &h6303B103, &h94B494E5, &h1E1FFC42, &h62C5A559
Data &h37385511, &h9369BD68, &h38970A27, &hD93B7D3E, &h4CF0B66F, &h1CCF7AA5
Data &h66716862, &hC4A4AC2D, &hFA539791, &h9C97316B, &h674204DE, &h9E2F40FB
Data &h05707697, &h5EEACEAB, &h3C0835AC, &hCB9B0B5C, &hA904C8FD, &h36CDECF3
Data &h79068645, &h1508F651, &h331F5F3C, &hC5F78659, &h1A4D9452, &h8C30C192
Data &hA5697853, &h1C770505, &hE0F59352, &h1ED5D441, &hCA26895B, &hC8810EC4
Data &h716AE175, &hDB372E4F, &h0947ED8A, &h6BFF2767, &h74630F9C, &h04E9D31A
Data &h89E75334, &h9C6FFBF7, &h6485BFDB, &h12B22B90, &hEA35306E, &h94B5591C
Data &h08AB0D55, &hE9C63A7D, &h1CBF0E9E, &h3B24C670, &h4F985472, &hA32AEA9A
Data &hCF6B27DE, &h9A6B873F, &h0FAB282A, &hDFB4369C, &hE48EB246, &h87053597
Data &h562CB2BF, &h018DC31F, &h3BD148E8, &h25D43324, &h03CC2957, &hFF20BD85
Data &h7F8A79C2, &hF9BA4437, &h71D0946D, &hDE6C0DE3, &h2FF6AD1F, &hF964368C
Data &h15AC1EF5, &h645B9E03, &hFAF556BA, &hCF99E1B0, &h525F6F8F, &hEFFF51A5
Data &hE4ABADE5, &h445399D4, &hBA6E89F2, &hD371833D, &h70E2238D, &hC59EB670
Data &h0B021292, &h7AD6453E, &h7EC213AD, &h3873448E, &h9BB4464B, &h518C3500
Data &hB2FCBBB4, &h2BBF6B1A, &h18D1561E, &hF36B4DCE, &hD44746AA, &h1DF79F90
Data &h86BD7D1F, &h95DB39DA, &hDD6599D9, &h6A721D71, &h4D4FF264, &hFEE5AF59
Data &hC2863C94, &hC8BB0527, &h2B4256C0, &h37436A44, &hA93F215E, &h539B1510
Data &hFC87E2B1, &h9DF72E91, &h4B33A4D8, &h3B3EBF9D, &h83B4E3EA, &hB3B0E76F
Data &h3AF176B7, &h2B4E346A, &h4E568189, &hF2EBD2C5, &h8B82C14B, &hF70BA10D
Data &h66FFE6B1, &hBF5A6A62, &h09B37097, &h2F89DD9A, &h90F9DE65, &h1C41D0BD
Data &h91556DA6, &hCD486FE6, &hED6C3A4B, &h9C3D19E2, &h012E2FDC, &h96C06730
Data &h386B863E, &hD4F0E384, &hA36EF0E1, &h8017BD04, &hA005BB87, &hE5B3D18F
Data &h46A4CF18, &h481FD3D3, &h86D166FE, &h92C7BA6E, &h9B99AD9A, &h079A1C9B
Data &h1E3EBEBF, &h5B65F2EA, &hF42076D3, &hCB91D3B6, &h3441CA68, &h7292C022
Data &h94F01C23, &hBC98A222, &hB250C68B, &hD62B96E9, &h6900B8C6, &h451705CB
Data &h110B6598, &hED616CF4, &h29F92D70, &h4FA325C0, &hD14ED2CB, &h9F8E91E3
Data &hF15EC43D, &h002A644A, &hAB90DD73, &h17051404, &hEB3F9827, &hE2172F30
Data &hC4C282DA, &h525E2FD1, &hE70FA0C3, &hED7188A5, &h006E10E4, &h092AA669
Data &h20204546, &hB26E7EF3, &h69C6ACAB, &hF24A01BA, &h314746FA, &hC6FA7B57
Data &h25130993, &hBAF97BF3, &h35FA67BC, &hF1E8F0AC, &h2924ABA1, &h421EF39B
Data &h8632FF33, &hDB645103, &hBC6735CB, &h16777BBC, &h85493C0D, &hD65256BD
Data &h4D4ED25E, &hED05453D, &h7E28D08A, &hC38843DC, &h97D46B4F, &h076A7BEF
Data &hA30194D2, &h5F8B75F5, &h9904FF7C, &h424A371B, &h00EBD261, &h405C554A
Data &h71EC5E0B, &h6355D67E, &h02B237B3, &h408974DF, &hE9287323, &hD3424271
Data &h65619226, &h2992E3E2, &h65A885E4, &h023FA6F9, &h6D25FB42, &hB9237E85
Data &hA311A7DC, &hF30BC5EF, &hE2C7F594, &hD402254C, &h3B151C6E, &h3616B81C
Data &hD8D996EB, &h5735C3DA, &h9ACCE8DE, &hEDE84AB7, &hC228FAEB, &h86187D90
Data &hFAAA94D6, &h25D334F2, &hF6A9028D, &h638BAC1A, &h8E42B0AC, &h13CA2703
Data &h98A4A140, &hAE83E8E4, &hF1007E0C, &hDBBEBC8E, &h6A8FC14A, &h022D60F6
Data &h1785976F, &h75F015F5, &hA5C9C9F2, &h2B9EFD9B, &h4E1156B1, &hDF7A2CEF
Data &h7E54F7E2, &hED336C0C, &hED4CBB0E, &h7C0FA9F2, &hB8706B9F, &h787642E5
Data &hCB2CB500, &hA3D74838, &h3999D369, &hACA95A4E, &hCD9F938C, &hBDFC78F9
Data &h45649709, &h78F64761, &hDF86CA5A, &h83DC6652, &h780E9AC6, &hD9101314
Data &h7C269719, &h2B5FD878, &hB69E3F19, &h1A13FA5D, &h208EECD2, &h6B79E304
Data &h590610C0, &hF01C0588, &hD6DE95DA, &h984E11AB, &h6F326F1F, &hF416D0FF
Data &hACE826F8, &h3C381888, &h6450381D, &h41D65C35, &hA2947FFD, &hE26DA0E9
Data &h31B405E8, &h28CB542C, &h12841064, &h7DE4EBAB, &h096494D4, &h020DEA07
Data &hEF101BD3, &h4D8B07EB, &h0A831099, &h46942857, &h323C0F84, &hAE051D1F
Data &h0B770456, &h63DC508D, &h1954AD4F, &h4A1E6A48, &hC489FB80, &h705D6009
Data &h3974B018, &hCDB8A69D, &hA4803C58, &hD0CA0D26, &h76785105, &hFA4221AF
Data &h4B69F62F, &h64F77057, &h69A1FC7F, &hBBF561E0, &hABAD2009, &h0B1E23DB
Data &h2FE9D448, &h87621011, &hBB7C23B8, &h37D23A53, &hE0AAA020, &h5FA13C25
Data &h9F9E9BE4, &hD4971C74, &h9FB434A6, &hF69FB53B, &hA3D7F5F5, &hE89C213E
Data &hDB8D5902, &h5F611F9E, &h085D36E3, &hB9276D53, &hAF358325, &h2009ABB6
Data &hFA944EAD, &hD4832AB5, &hE634B81C, &h7B82512F, &h3B13A3B1, &h86D1C133
Data &hD14C53FC, &h7D48D683, &h58D93FFA, &h75531559, &hF6E1D2D0, &h93841487
Data &hB4F7E237, &h4237291C, &hF7A8AD58, &h6FA9DF9F, &hB512E97D, &hDEB1BB29
Data &h68BC8C7A, &h5E248A49, &hBC22D1A5, &h2EFB6B1F, &h489F7E4C, &hDABE295A
Data &h0BC85102, &hA9E03E55, &h6665FAB2, &h29300934, &h9E456850, &hAF6BFC7B
Data &hC8B3024B, &h8AE3EE05, &h3DDEA7D8, &hD55A3F8B, &h12E1B5E1, &h33154791
Data &hDF090625, &hA66880D7, &h9DE41E04, &hD5F88447, &h67252409, &hF87F9B15
Data &h28F4EC26, &hBF2D0953, &hD035912B, &h30AD1021, &h61163EB0, &hA3EE960F
Data &hE0FEB39D, &hE9C8E401, &h7EACF44F, &h986387E8, &h518AEE46, &h767ABC41
Data &hA0355A46, &h7D284CA2, &h065B19CF, &hCEFDF9E0, &hE72A7424, &h328C88AC
Data &hFDB9C612, &hF5E22646, &hCDFF8947, &hB8D48B35, &h10AC7B5E, &hC4C61CCB
Data &hCDAC635F, &h9C73DE02, &hB30773F7, &h8B43D244, &hE922D7B0, &hB7D2A519
Data &h2D4F929E, &hACF2D7CA, &h334AA176, &h7E1C82FE, &h4BA47CC5, &h7B56EAF2
Data &hCAA6302B, &hFEA61C6F, &hB1AD1ECE, &h5FD5CB83, &h9A04D82B, &hA6FFA068
Data &h1C9519AA, &h6D724497, &hF65937A8, &h0A25BA34, &h90C98F44, &h43D1E99F
Data &hB7D25BBD, &hA3EA0A96, &hA7A71A3E, &h704B820D, &h57F51B1A, &hAC1357C0
Data &h4DE68093, &h777C6790, &h841F0409, &hAD1683C8, &h2A734A92, &h034B24B6
Data &h7FDD50FD, &h6C8ACB1D, &h5423E5A0, &h560EE892, &h2236F2B7, &h98108103
Data &h2AD9B79F, &h0094BDBA, &hA21DFBB0, &hB392B0D3, &hC210358C, &hE117EAB7
Data &h7D44AB76, &h446E43E9, &hB7717ADE, &h95EFE3BC, &hA76DD3D0, &h25231A97
Data &h203EA06D, &h584D7C31, &hECB79C90, &hE0C8EDD6, &hE0E6CCCE, &h9F160993
Data &h176FF5EB, &h19460765, &h046E84FF, &hCBE93605, &h573F8F95, &hEA8FBD3D
Data &h1F2F876E, &h67D94511, &h3513CACD, &h7FC05DBC, &hFD3533CE, &h309993BB
Data &h2BFEB191, &hB967F889, &h2F9C6E10, &hAA919B3C, &h5B2E39BE, &hE4825301
Data &hF93FFC4C, &hA86892B0, &h6CBBB393, &h433ECB8B, &h684F1F8F, &hF4EA71B0
Data &h1E31598D, &hEE01FCDB, &h71BDABD9, &h96D5656A, &h6C0890AF, &h6E00D33D
Data &hBFB13299, &hE938AA7D, &hA4E21F21, &h17DE1146, &hEF17C480, &h91C52A25
Data &h1F13113C, &h90205A41, &h18452C1F, &h947BAB66, &hEF5CB4D7, &h41B018CD
Data &h8E248727, &h6936E37C, &hE793D9F8, &hEB55E64B, &hDD283982, &hBF6AA798
Data &hAFF23401, &h7CA5B803, &hA05594E4, &hAB1C1B56, &hAB13A654, &hE3698BD5
Data &hD27ECA3A, &h762F35E1, &h8B65009A, &h88719C8E, &hD45630D9, &h75E4D7F8
Data &h6BE2D70D, &hD2B63DBB, &hBF6CB2DD, &h29FC452B, &h3F1C0926, &h57231D3E
Data &hA9262C77, &h4F01FB51, &h6765157C, &h79471AE1, &h1D029C1B, &h4ABBDD09
Data &hD05B0C76, &hA163DCD9, &h78F56413, &h2F7DA198, &h24A67612, &h8A173E5B
Data &h35D8F669, &h7FE746D3, &hA073EC1D, &hEABDF572, &h427A48BE, &h20E77607
Data &h239F53F5, &h8959260A, &h4851CD12, &h4D44E15E, &h8DDF1215, &h71DBBE43
Data &h476B386D, &h406B1E0E, &h8C2EDC9C, &h3794E2FC, &h885A2151, &h15A921F2
Data &hAF267F11, &h88899D64, &h119C5CC8, &hDB4B28FD, &h6CCA651D, &hBADDEEDE
Data &hE1D5B506, &h2F87D65F, &h77DA9DE0, &h8BFBF3D2, &h249E5277, &hDC3B9528
Data &hBFC4F9E3, &hB2BA9A5C, &hEE53F93A, &h3BEA91B1, &hEE2D09A7, &h57CFADDB
Data &h3DB9BEED, &hA16DE822, &hFCE042EB, &h0B7BC7AA, &h2510E033, &hB3D4AAB8
Data &h685491FD, &h7B9DC762, &h413CA5DB, &h9AA6BC90, &h672D0202, &h848EBDA1
Data &hAD6E4850, &h674A95F8, &h37F0E75D, &hCC05C03B, &hB05835C4, &h5E839F6A
Data &hB5C75AA1, &h64C556C3, &hA82246D5, &h20857F69, &h9F768EF2, &hEEE9699B
Data &hFE4B0C35, &h37ED88AE, &h7B8D2113, &h913BD1E6, &hF832E8CA, &h2B40E349
Data &h59E2C5AB, &h439D580C, &hA5F8E27E, &h2D44B82A, &h882E225A, &h40FE0B19
Data &hE985CE8A, &h6E52E811, &h81D93D6F, &h9CB3C7E3, &h2A706A04, &h1320693D
Data &h9E9DCD77, &h837817E1, &h7F83E6ED, &h531D5D04, &hE37FBB3A, &h9AD01A98
Data &hB4315DE5, &h8B538543, &hE8D852F3, &hC28D7599, &h95094BD1, &h6A6F4498
Data &h0335594B, &h39624196, &hF974D07A, &hDADF170D, &h8E5D5D92, &hB8F537FF
Data &hBB0F703F, &h061D566D, &h25FA8689, &h3674F4B5, &hF6B3BADC, &h4364D775
Data &hA1668522, &hB20A05B6, &hEE2E8615, &h7100B27F, &hC1456939, &hC4E563BE
Data &hDD141B06, &h64F26EA3, &hD2000A97, &h6C567BED, &hA94D4BF1, &h8F016C07
Data &h8468CD53, &h2E57110B, &h4EC225B4, &hFECBE7AF, &hA5F95178, &h70C3DD92
Data &h0085E8E0, &h08DB7AE0, &hAA5CA065, &h8E9148FA, &hAE2E0C86, &h442A8CB4
Data &h5E111CC6, &h1DD864F9, &h43D68703, &h7E6A25F6, &hE2560409, &h93495922
Data &h64D3211D, &h299455A5, &h74DDAB4B, &hD023F331, &h1351FD4D, &h66CE28B5
Data &h50F1F3DB, &h5A843329, &hED29FA1E, &h2A8919EC, &h9485DB04, &hCFFADA67
Data &hCD0D1180, &h0E450711, &h053ABE25, &hDEEF0968, &h1075810B, &h685E4110
Data &hE9BDCD03, &h9BF5B2CD, &h97E23D1F, &h0D7E4A3C, &h9AC76787, &h876A3F99
Data &hF9E3D7BE, &hDE8BCE6B, &hD173FFC4, &hBC51279F, &h79E8696E, &hDDD323BC
Data &h31833467, &hB1046718, &h5D62BB60, &h096B0F09, &hB2A00F89, &hE3AB8C6C
Data &h3EA2129F, &hC707B6D9, &h741184F2, &hE3590F0A, &h8168646A, &hA95EC612
Data &hD7A2B4CF, &h75B051CA, &hABEBC792, &h3389D656, &h9143F48C, &hBAB3D89D
Data &hD873A5E7, &h5D08CE57, &h0EF72DCA, &h3CF7B95D, &hDE84218F, &h138E665B
Data &h8FD78B6B, &h54140F68, &hFDC89B5E, &hF64578AB, &h99E6BCF3, &h366A0C60
Data &h8F422D39, &h6A00529B, &h70A11A96, &hF083CCA8, &h44486C0D, &h37547A47
Data &hABA565C8, &hC229974D, &hD8043E7B, &hE9A12A9A, &h28BFD9BA, &hDA3352D8
Data &hD1029A1C, &h0B24868B, &hAAE998B5, &hFDA6D5D4, &h3B7F7118, &hF1ECB1F1
Data &h878E983B, &h2BC615FC, &h6F613DB3, &h2F0567DA, &hC0CCD17C, &h5718D32F
Data &hC73D2197, &h645E3635, &h644044D1, &h265172BA, &h639CC5DB, &hD4829334
Data &h5AA7E358, &h0553EE01, &hB4A3034C, &h19F57D4F, &h993DF573, &h7013D8B3
Data &h23E46471, &h966ABB82, &h9961A313, &hCC7A4A6B, &h2B1500E0, &h9B874311
Data &h5EBBAA3D, &hBA2B2737, &h09695E4E, &h5E3136B0, &h20F86764, &hB342A693
Data &hD511A80F, &h651CF45D, &h8CA47199, &h165BCFCC, &hBE7F3AAB, &hB9A84FAE
Data &hA9595FDB, &h6CE4A6AE, &h634BADD4, &hA6756EE2, &h732D5924, &h0810D0F4
Data &h9EE79C58, &hCD9AA37D, &h53DBB48D, &h79AB0265, &h06958739, &h50128210
Data &h93F82F3D, &h831A827B, &h6077D787, &hFE9C466D, &hC95CB8A3, &h8ECD17C4
Data &h42AA7DFA, &h41316C90, &hBA9E00CE, &h0FBCF181, &h472805E0, &hC16B72B3
Data &hF71CBAD2, &hD556EA18, &hFA1C9133, &hCE84FF33, &hD13E8E87, &h21A6FE5A
Data &h8239CDC0, &hB402FC39, &h48DC2443, &hE5E229C4, &h2E6D9B62, &h1EA4C766
Data &h7A21F097, &hDCF87B5B, &hD306B3EC, &h18842F74, &hFF59AF83, &h6E1B505B
Data &hF749A639, &h55363AA8, &hF9A8F890, &hF1169B1F, &h0A4CD87B, &hB4FDFA86
Data &h2BBD4153, &h0FFD388D, &hE11DAA1C, &h0DFE293D, &h81B43728, &h33EC9479
Data &hC6CB9B22, &h237D3921, &h73C3E340, &hE36F5629, &hE713F412, &h9051ABCC
Data &h730E42F5, &h4FEB1F6D, &h9C17E21D, &h2BC2C5BB, &h5CD99E0B, &h25C09E21
Data &hD16C082A, &hC2AE2B79, &hF888AA32, &h654BBE2F, &h55715D2B, &hC7CCCECE
Data &h05C0EB93, &hA7DED6AE, &hFE2BFAC6, &hA9F40041, &h5661F505, &hE1AFECAD
Data &hAF6586C6, &h9D48E300, &h589F24E4, &h22E15154, &hA1FC6457, &hF8AA9E2A
Data &h2266CB95, &hB82C64BC, &hA22C459D, &h225BF00B, &h7924D567, &h7F7BB756
Data &h6DFCF3E7, &hF492ECD5, &h02DF9287, &h9C3042FF, &h6CF9582B, &h42D8D766
Data &h0C555E48, &h83E08551, &h9A47A6C1, &hE97A5A35, &h807C536E, &h9A5BDE99
Data &hCC8698D6, &h28127BD7, &h9F1A3CA9, &h0ED7532B, &h7434DC65, &h89CCD584
Data &hF1E7CDE7, &h6761C7E3, &h62833008, &hD656F1D6, &h31423DCE, &hB54BFB24
Data &hE9D3C134, &h352D5C76, &h933948E9, &h07E20867, &h86E0C9FA, &h85F9483B
Data &h6424656D, &h4184EDCC, &h08B6EC1D, &hEA79B807, &hFA270E98, &h99557E75
Data &h039F459C, &h3324C196, &hB0094FEF, &hB2B60A37, &h4E36F0F4, &hA0B9C172
Data &h48A16AB8, &hF9F01C17, &h0740D6C3, &hD03F6107, &h7F49E45E, &hD3125A08
Data &hC74750BC, &h9049744F, &hE9C21C08, &hDDF493B5, &hD0736E6C, &h1120C61B
Data &h7224E1A0, &h9408D12C, &h9AD73E86, &hF1877C28, &h7E3AEAEA, &h98E665BD
Data &h14BA9000, &h49894595, &h408C4CC6, &h1BA52FB2, &h3663C170, &hA7D74271
Data &h1D3483E5, &hA648D370, &h94D66A71, &hFB913B0E, &h8E54BFBB, &h6E34D5F7
Data &h43F764B3, &h4297F4E8, &hF5BFD179, &hB8C5035D, &h2F7AC590, &hFA9FDC1F
Data &h3F5540E7, &hB6E0A5D4, &hC6E1E00C, &h29D42931, &hC5292B32, &hA2C526D0
Data &h3E061B61, &h94FAAC2F, &hCE78B3B3, &h9B8ADE22, &h20415E82, &hA9C79FCD
Data &h517C99F2, &hDFE2057F, &h0BAFAA49, &h3634F5DD, &h48C8FD74, &hAB4CE406
Data &hD48F58F9, &h8A357F0E, &h793518B5, &hA1204AF1, &h9CE02504, &hFC35DC44
Data &hFC3AA9EA, &h1CD46AD8, &h0A6CEAC6, &h00681D33, &h2562DC98, &h8B6D6CC1
Data &h8EAEF542, &h7533A88A, &h907D735E, &h65A366D6, &h034A1BDD, &h6FA5E767
Data &h8E7819D7, &hFF9EB20C, &h56B8F983, &hC97E5B54, &hFBDADE18, &h73EA703F
Data &hF48BCA17, &h59A3AB16, &h5EF8E7C4, &h5B633478, &h5CD3B6F3, &h6DCD478E
Data &hF644D198, &h04DFABF5, &hA27DABE8, &h609DEAE1, &hF8E84E9E, &h1BAAC888
Data &hFF32F6FD, &hC7E2AE3E, &hED20596A, &h18704F5E, &h1A2EF5D6, &h5FDED7F5
Data &hF4DF01B9, &hF3F6760A, &hE4A1FACA, &h04D035EC, &h12F7E5CA, &h3A61788B
Data &hFDFC67C6, &h86074186, &h2C335E39, &hF4C34351, &h8B6F280F, &h71FB1EB9
Data &h43AF7617, &hD7EC8F68, &hA2C9DCA5, &h0A558E77, &h4BBE81A5, &hBAFE584F
Data &h9D6343EE, &h1F71D2CD, &h03588805, &h8A3789EE, &h24BAAE01, &h6FFB1329
Data &h8AD34C53, &hACD50FE5, &h22393383, &h588A8538, &h354D91E4, &h0F87293F
Data &h7BC85EE9, &h76DCED6A, &h2E0A98DC, &h2AAFD480, &h03E830B9, &hFAC3484C
Data &hB7FEA6E9, &hB90D52E9, &hF94F3A2C, &hAE104638, &hAF34B9C3, &h05ADF232
Data &hA1695399, &h3201E1D4, &hA0A0CDFB, &h5CADC5E4, &hF37F80E1, &hBDE5D2C4
Data &hC866FAA8, &hB3E63BEB, &hDFEC0BA5, &h7B83414B, &h8766A376, &h986104BE
Data &h7F7E7088, &h7560A70C, &hA37C9573, &hD83CE015, &h30DC59C7, &hED38A7E3
Data &hBA7CE12B, &h35D52A5F, &h1A584182, &h1E1365B5, &h818B115D, &h630B63E8
Data &h7BDE5E7C, &hCAA353AD, &hA0CC939B, &hF12177E3, &h139CE7AD, &h9446B98E
Data &hFBB6C35F, &hB3859AFD, &h95946173, &h99D588FB, &h7B27F61C, &h1A10E247
Data &h81E86A13, &h1F37BCC2, &h5D733DBC, &h9E362E39, &h7182EBEE, &hC8D4EDE7
Data &h092F1136, &h8A1F4DD8, &h3A20CFDA, &h3BB8825B, &h92F34574, &h94422A7E
Data &hAC3A15CA, &hCFABEB6A, &h70F83CB9, &h97454F71, &hC56B9A04, &hC6F82373
Data &h2D5282CE, &hDE74259B, &h2C1A421C, &h0789F0B2, &h99D96765, &hD56BBBA6
Data &h75AD66BE, &h09128BDE, &hB4EACF6F, &hAC363E0C, &hE292DF06, &h9364C3F5
Data &h1D58E597, &h9087472B, &h7DAA4EDB, &h4CC7CC30, &hF9D7F743, &hB46CB80E
Data &hF252BE26, &hF4C8067F, &hC3D8DAAF, &h48EF530F, &hEEAD5B25, &h3F2A2A83
Data &h1AFB1B5B, &hBFA9AD4B, &hC3D40435, &h2F1DCB07, &h9F021AEE, &h5733E94B
Data &hACA1AEC3, &h18ACF23C, &h87A3A85E, &h3354E129, &h43BB28CD, &h02321CC4
Data &h800DB69D, &h06E29317, &h13B633B1, &hEB53F7F0, &h50109724, &hCFDC2B49
Data &h0B4F6230, &h4B5E6D39, &hE312356B, &hD9DD1D55, &h7BB0C050, &hD19D7C4F
Data &hEFB5B702, &h57C7A13B, &hAF9FA674, &h5D7321B3, &h78545042, &h9BADF3C7
Data &hB9CB73D1, &h2DDE3C8F, &hF4B45AC7, &hB038A709, &h9B9B9C97, &hDB3570B9
Data &h73EA5226, &h4482F6C1, &hB20B4333, &hF7967E5B, &h813435B7, &h314CCDCD
Data &h01CA7DC5, &hD21E8025, &h02D4B7D2, &h93673A08, &hBB321757, &h59CA3CCE
Data &hDB827F79, &h8B1304EA, &h912CBFA1, &hDEF02712, &h72EFF9A4, &h3C2DC8BA
Data &hCD1D3526, &h3143CE03, &hDCDAF18A, &h2064D1C4, &h39984590, &h47F4D6DE
Data &h0F0DADEA, &h4C70FC48, &hB181283E, &h72251F69, &h49DCE444, &h164533BB
Data &h682924AA, &h371693FC, &hF88A895E, &h9E015B0D, &h45DAE321, &hF7BB4ABA
Data &hC0B7467F, &h6C25E5C8, &h0950FC5F, &hD728AC47, &h7AA2980C, &hCB7F8864
Data &h595B6370, &hAE969C4A, &hDD5DD3D3, &hF0BBA132, &h8040A227, &hB298793C
Data &h609F9D19, &h40F7001F, &h44826BCD, &h4FC66DE0, &h4B39E9C2, &h90421D35
Data &hBD2893AB, &h7D08BA43, &h5E4B1ED3, &h2707DC6E, &h6B9155E5, &h6809887F
Data &h723B15EB, &h7606906D, &h13408416, &hB9EEA6ED, &h6DAA1F44, &hB7080A44
Data &h998FF33E, &hFFC88BAB, &hCA68F8C4, &h43195BF1, &h2AA848E7, &hBFE35DEE
Data &h2D807BF7, &h18E0B5BB, &h587C7854, &h3AC7E938, &hD207E37F, &h7644EB8A
Data &h41315260, &h7FEE09E6, &h6F994B90, &hB2EC9BD4, &h462133F1, &h888B3763
Data &h34F055DD, &hDF386C03, &hF16C2491, &h1C91EE01, &h7C173A52, &h79633CDD
Data &hBF10E087, &h65844D3E, &h22388335, &h6FA51358, &h0405EF6B, &hCB931C4D
Data &h76D3D174, &h9E7DDE68, &h51C72885, &h733219FF, &h0320F3DC, &hFAB5B67F
Data &hA847F8E2, &hDACA6084, &hECC77EE4, &h6A9308D3, &h0B0FB30E, &h8110A502
Data &h4E97E885, &h2E9F9D18, &h2C3A2CCE, &h2D374AA3, &hB4ECC25B, &hD2ED62B8
Data &hCA8AA8B7, &hE5AFEB81, &hC89B09F4, &h0BFA6581, &h43230649, &h5F1DD038
Data &h4AFE2A62, &h1A6CD2B8, &hC0014BA4, &h58650038, &h97DBB90F, &hA6EB4115
Data &h923BCB43, &h9B0D316A, &h82B888F4, &h7E9E707D, &h5A00A492, &h44DE9631
Data &hB3C2A67F, &hAEA508DA, &hD70EC840, &h27181220, &h657C5731, &h71CD6492
Data &hD815838D, &hE0017923, &hD46CF726, &h21180C06, &hCAEEF80E, &h2403DBFA
Data &h18822AD1, &h966787A3, &h8C43FF34, &h7805DC84, &h24FD660B, &hA3BAE6FF
Data &h8EE6BE29, &h32AFB016, &hFAC6B93F, &hF02ED441, &hE04DC633, &h3B113DF5
Data &h935F68B8, &h72E4C6F6, &h585DC084, &hE37E0D96, &h332684E0, &h2415C896
Data &h9D513499, &h97B714B9, &hEFE08204, &h982C1849, &hB52749BB, &hABBD6554
Data &h58CD8018, &h6C63A5DB, &hDB6C293C, &h49D46642, &hC3FCAB21, &hAB2863A1
Data &h9B4F29F4, &h024E83FF, &h4952622F, &h52B15F7E, &h79973EDE, &hF12B2AD9
Data &h00D475D9, &h4C4767A2, &h26C906CC, &hB9B0B24C, &hEB04BBB7, &hAB5E6D2D
Data &h5520EC19, &hE3CDE047, &h314E3B83, &hF46FD249, &h491FB1C8, &h31B9BD48
Data &h11A07CD4, &h42940E37, &hFD32D08E, &h7C205BDE, &hBE286BC5, &h15C95305
Data &h557BA6AC, &h0C4834E9, &h5CDEC695, &hED0223DB, &h49EEF4EA, &hE85774FE
Data &h7CBEFE61, &hE8460A82, &h0381961A, &hBE0B14CF, &hE839F152, &h002E8CC0
Data &h7D43EAC8, &hE03EDC03, &hAC749FCD, &h4ECEA723, &hABF82F37, &h1641320D
Data &h3E9F9FD8, &h7FA9B261, &h96A5CB98, &hD08FC398, &h52983493, &hFF4C9E8E
Data &h0405343D, &h34CCF776, &h856DB7E7, &h42121766, &h5B1915F6, &h3464F16E
Data &h52E22EEA, &hDE253CB3, &hCF629230, &h7E38C7F5, &h7E8DBF5E, &h070765D4
Data &hE18A5F4D, &hDAD8B3BE, &h21DAE735, &h7801C326, &hAF5296C3, &hF417B902
Data &h3DD5B2E2, &h5494ABAD, &hD99386FD, &hC1A80127, &h8D4E6BEC, &hCA773B8C
Data &hF0A0C662, &hEE985C98, &h912B6535, &h400FC6B8, &hD8A0D334, &hF2631ED5
Data &h8D304689, &h0578C3A0, &h0E86598B, &h54818E2C, &h4C0092BD, &hA9E03616
Data &h321491C9, &hCFAE8BF8, &h99D05EC3, &h3137D8D4, &h2DA92859, &h68C2A5A7
Data &h2784BC3C, &h0B785010, &h83BEA16A, &hB845D1FD, &h75F0A827, &h88546859
Data &hFE4820A6, &h01F8D10F, &hD8E3A697, &hA9E86D44, &hF11A8E21, &h500ECB1A
Data &h7A43114F, &h72687BD4, &hB50E22EA, &hFF487C34, &hEA164BB8, &hC1151A40
Data &h4F0F86F7, &h238923C3, &hC576CD97, &h2D9ED314, &h990FB6D2, &hEC583438
Data &h58A9C931, &h1776AD37, &h58FED323, &h19AF2ECE, &hEAAC066E, &hC4B7F7C5
Data &hA7DD4AF1, &h3B423D4D, &h3EB1A7CB, &hE1E8FBB6, &h86814607, &h204E3030
Data &h8601C511, &h29F5691B, &h96A35A36, &h3EE949CB, &hBD65B41F, &hE9D7B5F6
Data &h68A86E25, &h3911C6EA, &h17FC16A5, &h6D82E2E7, &hF612B574, &h7EE14BAB
Data &hB7ABA1A1, &hB46593FC, &hE7E0A157, &hEE864DA4, &hE58F991C, &h02DCF8DE
Data &hBAEB6854, &hF8FC04CC, &h782A92B1, &hC2F7DA1E, &h056D8F6F, &hE26EB899
Data &h29076030, &h4B37EA67, &h29865E39, &h5609FE74, &h08FA4E3B, &h56E0C5BE
Data &h47AC24FB, &hFD65799E, &hE686F8BB, &hFE52D2D0, &h8E6F5D53, &h572B7503
Data &h3CD13509, &h0501FCA7, &hE3BDFA90, &hB05B01A2, &h082F5CD5, &h8E4D5312
Data &h3B402F61, &h8729A48D, &h06DF64CD, &hFDE8C94A, &h67C012B6, &h23384491
Data &h866659AF, &hFE77B57B, &h638BD6EF, &h1B6D0DC3, &hAE49BF84, &h0C7E7CF8
Data &h53EA1071, &h0B6DE795, &h87D8FF85, &h5F12EE76, &hDB56714A, &hA466D443
Data &h4ECD1157, &hC174C16A, &h41869BB5, &hC93F9CE4, &h77132D5D, &h63DFA85C
Data &h987F52AB, &h26AFDC9B, &hB9ED1771, &hBA395524, &hDC694340, &h249DE727
Data &hC3C6C037, &h20D9A09F, &hCDCF2F56, &h7E216996, &h70E1964B, &h123FB468
Data &h705D1EEE, &hED8E3313, &h350EFE0A, &h587FE358, &h748D4261, &h6EBB8D99
Data &h1FDCFC19, &h081F2B87, &h20CECDA8, &h87EE521D, &hD2B06A3D, &h5DA5430F
Data &hC7FAD081, &hA638FFD5, &h1C696346, &hB9D61AC8, &hC593EB31, &hF2F0AC5E
Data &hDA59E4CE, &hB302DADC, &h4F36AF46, &h79CA993C, &h284B7B83, &h7A83AE5D
Data &hB2BEA4B0, &h18479691, &hBAE63AE0, &h7802067F, &h2A16902A, &hB0AAB37C
Data &hD99D9E2C, &h93CC8637, &hBBA25F76, &hA2F2E280, &hE326531B, &hA865F839
Data &h5E220F42, &h94429BC8, &hB54B8716, &h969E59AA, &hFD9EC15F, &h98FA2249
Data &h650E1246, &h9A47437D, &h12EFE82D, &hB55C7A42, &h556F4B21, &h55CF345C
Data &h64616DE3, &hF81443F3, &hFC139404, &hD6D70AED, &hBA735114, &h0CD8C051
Data &hA6A2EE5D, &h1B9E112E, &h267B07DA, &h15057DB6, &h4565FDFE, &h29C7196D
Data &h53681239, &h6F912B94, &h609A160D, &h6D800735, &hA091EFBE, &h4D5F8EEE
Data &hF27B5D16, &hCBD784C3, &h725599E2, &h40824AF1, &h246221B7, &h9DC8E072
Data &hFA4306CD, &h054C2022, &h460B69DA, &hE81D8CA1, &hABC47F48, &h17C6546F
Data &hE5842518, &hA0CFA055, &h2A388C7B, &hA8EBE25D, &h47113484, &hF7F85F59
Data &h57233A27, &h7133E8B1, &h5D195ED9, &h271ABA5D, &h16017759, &hAF21FD9B
Data &hA4F535EA, &h8AA80104, &h1BF65449, &hE759291C, &h3887A4EB, &h90E0B216
Data &h9A94A7CD, &hAD56B4B5, &h575538C9, &h63B09E81, &h2BB614CC, &hDC0A308D
Data &hFA73D56D, &h979E252E, &h2227C748, &h187C7687, &h15AB66EF, &hE7A781C9
Data &hB79DF9CE, &hF889F6C9, &h20C4FE33, &h1677CC74, &hC197AE81, &h70425FF9
Data &h6E16950B, &hC1408EA7, &hE3D3DB03, &hAB38C753, &h426E0C94, &h17209FB9
Data &h1F9B52B0, &h139209C3, &hDF8AA1BC, &h181DAD89, &h9FD0F526, &hFF16FDC3
Data &h705E6ADA, &h3492D6CF, &h21C4A774, &hF35E0418, &h547E8297, &hEAE9A3A9
Data &h8C292F12, &h3692BA51, &h3B494C8C, &hCE0CA577, &h770BCAAD, &hEB9A7E80
Data &h61BCA3AF, &hFDF9F068, &h25AE270D, &h1FEF254B, &hFE653CF6, &h1346F574
Data &hEA444E90, &hE944E6FB, &h438A7EB4, &h896F1F52, &hDBA47704, &hBB422668
Data &h82D9892A, &h7B723FEC, &h2117AEBC, &h33252304, &h0F1CAF54, &h634485EF
Data &h757DAE35, &hC469B825, &h93BD0FAA, &h73BEDDA8, &h780976BD, &hC80B520E
Data &h5140EA40, &h9ECC266F, &h31A62205, &hFAD36126, &h48F599DD, &hAFF07093
Data &h8F688CCF, &hEE75E909, &h517CD448, &hAC25D5AE, &h0247D70B, &hD0E5AB60
Data &hFBC84BF2, &hAC975D9E, &h405D5EE6, &hF1810009, &hB395EFE8, &h294214C4
Data &hAB48934D, &h69A378B2, &hBFAFEAC3, &hD39BAD4B, &h74B4B02C, &h5BE6854D
Data &hBF80536D, &hF6A4A6AD, &hFD94FF8A, &h77924D05, &h1595B6B5, &h78BAB76D
Data &hB56E4AD8, &hFD230CF6, &h72481D28, &hA53AD729, &hDFC86146, &hE0AACDE5
Data &hD7FDC341, &hF30BD650, &hEE4A9595, &h2CD7C638, &hC7FAE696, &h53BEC72F
Data &hFF5FFC46, &hEE2579F7, &h9D499710, &h3801FFFC, &h81E8DD30, &h6FBD3301
Data &h596877E6, &h07369095, &h598AB1C2, &h5A4DB1C2, &h5C7BD783, &hB8415CA5
Data &h24346FFA, &hB97CFF09, &hA0BB0977, &hFE8CB667, &h3ABC36B2, &hDFF32368
Data &h58E48BC7, &hCC4CE086, &h3D117DC2, &h0A521723, &h1280AC2B, &hE3D6D020
Data &hC43B587F, &hF8665969, &h0BF4A09E, &h5CF98CAB, &h0F6408E4, &hBBAF7882
Data &h215F4D6E, &h289C1E1F, &h2CE2EDC3, &h4D0CB186, &h32010400, &hD6508AAD
Data &h5578FD68, &h9DFB83DD, &h86A5C4FF, &h1FF22D30, &hCF340502, &hBE716A10
Data &hB7CDD584, &h75111F59, &hDCCE83F1, &h1F47C018, &h24EBA4DB, &h96B6765E
Data &h40338A05, &h8572EE9A, &h4C6EE5DC, &h8F76FD15, &h20E974D3, &h984C7FFA
Data &h6CB352CF, &h0BFA87D4, &hC2B24DA4, &hFD1A2456, &h2FDEF22A, &h72AB7F7A
Data &hDBD26ABA, &h710B7915, &hD6D5D86E, &h97ED934C, &h8D6C9474, &hD62BB26F
Data &h2AC7DBFD, &h1D4E045C, &h1F4A898E, &h398EFCA6, &h4650FE8A, &h4299EF20
Data &h47FF1569, &h9F82C734, &hB0C85C59, &h8237AC79, &h255DCD16, &h96B57E4A
Data &h16A1A8CB, &hD8F0F4D3, &h04BC3FD3, &h8EDC0844, &h0DCF26BB, &h30BE7CE3
Data &hE0A3CBBB, &h29303743, &h4B8B4B8C, &h4C184443, &h4096945A, &h7DF05AC7
Data &h4D3E8359, &hCDDEF291, &h13A34A02, &hC48A23B1, &hD75EF8DE, &hA1730B45
Data &hF51309C6, &h5D3A7BC9, &h42360DB6, &h6E1FB5EC, &h46CA018A, &h8254023D
Data &hE95B9BEF, &h6843FF48, &h3C812DC0, &h9206ABAD, &hD4E30EE4, &h21578FE3
Data &h3EBF6A0D, &h38BD0063, &h0DC4E6B6, &h1D514F3E, &hFB291E1F, &h18BA6213
Data &h0FD79251, &h6E35FC60, &hD5F695D7, &hCC84F213, &h7EA3F3A7, &h347F3C13
Data &h740C6139, &h44CB23E8, &h1DD114A0, &h092337EF, &hE0EBA98A, &h05724299
Data &h344EB4F7, &hE2FF21E2, &h65CEE7C3, &hB57D6DC7, &h3D09C76F, &hB4A31873
Data &h7B253162, &hCDEBF02D, &h05AFAB7E, &hC661925C, &h79546692, &hFE06C382
Data &h7FD731DB, &hECF44276, &hEA445689, &h6AFBFDD5, &h9D44072A, &hD4DE7695
Data &hD1DF1DCF, &h1C5CB520, &h4F1D327F, &h6D5994D0, &h7210BC15, &h4499BA95
Data &h53C8D93E, &h2188F99D, &hE968FA15, &hB3C182A9, &h3B01C111, &hB1893C00
Data &h216289D0, &h1999DCA5, &hFCDD54F6, &h7F46C358, &h2D85E31A, &hED7E1C20
Data &hCAC44368, &h876337C8, &h274071D5, &h5446BFD0, &h37F84998, &h8E6866BD
Data &hD6CBBCDC, &hFBF21CFF, &h6E34B382, &hE93CA2E0, &h3E527736, &hB5276C5A
Data &h806EC66B, &h1F0C8410, &hEE32DC71, &hAF049DC5, &hBDB1FAB1, &hB4B5AC78
Data &h355996D0, &h6F59B46E, &h826941BB, &h9F271B42, &hB26DCDC4, &h4670FB24
Data &h2812D800, &hA2C3C778, &hCF9DD6E9, &h55A2D1D3, &hC389C230, &hCCBC6803
Data &h0C9DAB0E, &hA25FEDB0, &h9B2835B8, &hDE0CEE4F, &h705831F3, &h3958C7F2
Data &hCEE40D9B, &hACD5BA4D, &hF85794F2, &hE512D05E, &h92B94A61, &hE094104C
Data &h079E1F6D, &h4A417E84, &h8EAB1F30, &hB1150F6E, &hAE9BD085, &hDBD219D7
Data &hD23F351A, &hE9650107, &hB70BD1BF, &hC03EAA7E, &hCD1DB1F2, &hCA934788
Data &h280BCC93, &hA8576816, &hEFE3133F, &h1DFFEB55, &h5862B4D4, &h832B93AD
Data &hEFFF82E7, &h86E6C53D, &hDC5F4B5B, &h95678F08, &h078E2AA3, &h75A807DF
Data &h5B51FDE3, &h510903A0, &h5AFC0508, &hF8460B2A, &h5F34EAD7, &h57711067
Data &hED140DD2, &hBA993CFB, &hDF6E49F4, &hA9B444F0, &hF11DA5F0, &h01C5F47A
Data &h2A1D4D87, &h8A616CEA, &h07444540, &hF31194C8, &hF5950256, &h954C1D6A
Data &h5EBB4468, &hCD70A67E, &h5A4D6848, &h815679EB, &h8C497634, &hD0D47133
Data &hD10C5237, &h70CF3657, &h78605DBD, &h72903C75, &h05886F38, &hFB27FF1C
Data &h42C2CA4C, &h9EED7A7C, &hFA428892, &h27615A6B, &hD73BA82E, &h1D6A16F9
Data &h51D61F14, &h0ED15283, &hE1C825A0, &h589ADBE2, &hA8F22BE3, &h614F959C
Data &h346475FC, &hDB776024, &h6D8D7485, &h80925E5F, &h86F93C49, &hCD276FC5
Data &hABA210AE, &h383CFEAB, &hC2E3897B, &hBE0C64BC, &hE85DE001, &h63FE3A20
Data &h2AD2C895, &hFAC5CF36, &hF23A586E, &h08230FF6, &h5657D9F3, &hA65AB5CE
Data &h3638EF0E, &h6B48DDC1, &h71784770, &h97976BEC, &hA7BC8C4E, &hF841E248
Data &h2C3FCA2F, &hA61BF6E4, &h9808F282, &hC610E4CD, &hACD99B78, &h63F3A7BB
Data &h3F934646, &h2BB19C44, &h64C56A96, &h9530CA0E, &h88298D99, &hD22D824E
Data &hBCC431BF, &h0B65E47D, &h31B0C456, &h6D2E3C7B, &h0CDC2ABD, &h30AB43CA
Data &hDAC85BA7, &h1E522E07, &hF82ADF5C, &hC44B11E2, &h4D95A92B, &hE7C95BD4
Data &h83447A06, &h24B1C1E2, &h55006D5C, &hBF3FBD61, &hB4849D38, &h5C64FE42
Data &hC83656F0, &h44B1F188, &h926E4BB6, &hDD6A4E0C, &hC8E2F547, &h0514C16D
Data &h87A12506, &hEF36B0DC, &h22190E52, &hB8FEBC05, &h22A19419, &h092074D8
Data &h95453C0F, &h41B88AA6, &h8C298BF4, &hA4196A48, &h02077D68, &h9954A51A
Data &hA987788F, &h9F0921D7, &hF660D38D, &h3A511831, &h0445DEFD, &h1FFB6359
Data &h5F6786E5, &hEA039559, &h08648740, &h25A9057C, &h834CD59E, &hDB896456
Data &hE4B9A7F3, &h6CCFBA71, &hE766FC63, &h1EFBB2A1, &hC4CACD12, &h489A014E
Data &h17F9D766, &hC7525450, &h4C8C3CFD, &hB7FF1F28, &h4222CC10, &h2D792BE6
Data &h2D4A19F2, &h1F55BA67, &h69971503, &hB1B21CDD, &h8E7618EF, &h875A6B50
Data &h841BC6EE, &h173DDF18, &hF464F7D6, &h018CBAB8, &hFC41C67B, &hD8743E81
Data &h93E62CBD, &h0705414A, &h2E361F60, &hAF5B3F9A, &h1940D32F, &hF2821200
Data &hD50D5353, &h2CCC3208, &hBFBF505D, &h27D666D9, &h866E7273, &h3D3A3152
Data &h07A7F0A3, &hB961188F, &hCC82AB1B, &hB8AD3F2C, &hCA370822, &h25537D96
Data &h5F01E957, &hEB5E7A05, &hD0566790, &hDD0E546B, &h5DBB7789, &h4CFFF87A
Data &hC73109B5, &h1BED09D2, &h4E81C971, &h99B7C92B, &h60C61EDD, &h8231EAA5
Data &hD337855C, &hB7CA5B9A, &h7224EFE6, &hF6CD322A, &h20B219BA, &h7361D912
Data &hD8630453, &hF48D3E25, &hDE8160FB, &h6B64BAA3, &h255F04BD, &hCB89608D
Data &h267AE250, &h7BFA5508, &hECCF0B84, &hF31165DA, &h2B1030A1, &h9F519B34
Data &h58195AF3, &h8709A3FB, &hDF6535D5, &h56DABCFC, &h02F0EF50, &hF6C6347C
Data &h21273771, &hC2328FC4, &h12CB1D9B, &hCCEE347B, &hEA4C7634, &hB5DC4B5A
Data &h31203BA9, &hC0B30476, &h32B62188, &hE22A5714, &h72148F89, &h4227EAAF
Data &h2FE8C4AB, &h06E38E18, &h26D6C15E, &h7D4999B9, &h1FF9C5DF, &h0CB0CAF1
Data &h3EFC4AA7, &h00CF9EA3, &hC123ADB0, &h94BE5627, &h5F66443C, &h2B26877D
Data &hAEC7FC69, &hAF532D8A, &hAA604209, &h95C10056, &hB18A703D, &h81AECA9B
Data &h58A5598C, &hC247DC21, &hC42EEC47, &h28D3A2A2, &hE4C62ED5, &h2D1878FA
Data &h9FE991EB, &hE7CB9ACD, &h3D7D2C09, &hA181703D, &h85CB3BDE, &hF23BE1E1
Data &h7283C4B1, &h6FE62D87, &hEC44736E, &h81D1260E, &h02903AB4, &h1CD6FC17
Data &h58CBA1E7, &hEBEA1733, &hAE01E5F6, &h964CCE9D, &h7DDF7BF0, &h1E342726
Data &h9CFFC97C, &h90079173, &h27A32DF7, &hDA8EBC10, &h9EB46D27, &h493564ED
Data &hE2FCD899, &h488765F1, &hC8D55683, &h59BA7845, &h7F7CCDC4, &hB370936F
Data &h9E914841, &hD4CCD08E, &h9AD72708, &h46E59D3F, &h8D9D1C78, &hA0925C44
Data &h0493C6D2, &hB2BC4167, &h232C0BB8, &hE48E9A78, &h561557D9, &hD6EC2305
Data &h846A8F39, &hD2BDABFD, &h9532CDE6, &h09A07BC5, &h790EA455, &h02CFE6A0
Data &h852CE4BA, &h38C8D67D, &hC66C1CE5, &h4F3A628B, &h5F4E82F1, &h72048B0E
Data &h49C987A2, &h1650F3EA, &h489AD5F9, &h0A43F948, &hDEDE7D4F, &h88B85E94
Data &hCD3A5ADD, &h3A8E0573, &h664196EC, &h2C29636A, &h4BB6E309, &h91A9A8CE
Data &h6AA858CD, &hDF05B43C, &hA6D29891, &h14C06356, &h8A1830DD, &h73E47092
Data &hDBB80222, &hA648665C, &h67E6E036, &hED499821, &hA8241B85, &h913E87CC
Data &hF33312A2, &hA44D01A3, &h663133B9, &hEDD0DF4C, &h2BDB7D0B, &h3E2DA9BA
Data &h76DC41D8, &h004F9946, &h1E84A543, &h0F53B158, &h75660668, &hE9B49D3A
Data &h271DF3FF, &hF2A66F7F, &h1F450360, &h17B1811F, &h745923BA, &h38129117
Data &h2F9EF579, &hDE2C2386, &h108D8FCA, &h23C7FE91, &h3C89F6C4, &h2C14990D
Data &h64F99376, &hCAE24492, &hF234A241, &h39A3A839, &h935A4920, &h97B9F4AA
Data &hE1436A5F, &h27AB037F, &hEB1961BE, &h00C934CB, &h30A1B11B, &h8D1C755D
Data &h3E37AB61, &hE10A9BFD, &h494D668F, &h4D94C220, &hA00A9DA8, &h5D4115B5
Data &hFC4C72FD, &h71A5094D, &hA5C47E00, &hB5A7C1C9, &h36468858, &h09449D25
Data &h59ED65E0, &h28B60D30, &hEF2E2582, &hC3047F82, &hF7176ADE, &hBDEB78EB
Data &h2F388262, &h9A926075, &h5F1838C8, &h159BF0D3, &h29156631, &h938CC235
Data &h7D192EFF, &hE6BF8766, &h1C35883E, &h2503C9CD, &hCE13E3FB, &h7E50A8F7
Data &hED63E7AB, &h54D25E63, &h1A47D3BE, &h3F33C09D, &h1873A984, &h3CB06DCF
Data &h6C731F3D, &h7BA5F143, &h8A27C242, &hE38E35B4, &h80A19514, &hB890E620
Data &h69A07894, &h647482AC, &h8E1E5060, &hB7B9C4E5, &hBF96549E, &h0587D582
Data &h6BF38031, &hEE30DD46, &hE144B748, &h16E3A439, &h2D60A4BE, &hBF85DC14
Data &hA1B31B04, &h1BDC4594, &hBA6AA7F1, &hBF98764E, &h18206750, &h6491A56A
Data &h4D356E71, &hBBE00CF7, &hB3476003, &h7691516B, &h3048AAEF, &h8CF3F5E6
Data &h1197B76B, &h613222E7, &h8EF21F97, &hAB93ADCE, &hFF80FD0B, &h8D3AA0AC
Data &hDA85BDEA, &hDCDB5685, &h88C1B57B, &hEF50D1BB, &h37C4367A, &h7F5474A5
Data &hA3E85039, &hB7A9E657, &h7AEAFC98, &h9B16C1B9, &h4196F049, &hC19676E5
Data &hE6DA7211, &hC9513A15, &h0FC5AF7F, &h9ECF7DF1, &h3F187D42, &h97171665
Data &h2FC5A4BF, &hE18A7221, &h73836279, &hD33BAFD8, &hDC8E8D44, &h8B6BDFD9
Data &h1D4C816A, &hBD288C07, &h98E5AFFE, &hBE3E4BFF, &h2A4C1AB4, &hCCE7B0A3
Data &hD36524F8, &h67074587, &hC303DDFD, &hD6F6359F, &h13642CE6, &hDEF80EE8
Data &hEF2DC0BA, &h5D37DCFA, &h860237D6, &h07DA3199, &hF2415316, &h8FE72C0D
Data &h82831B6B, &h465D2EBB, &hE133A483, &h07B92126, &h2CBD7F7E, &h819DBD46
Data &h6345A6FF, &h588CCED5, &hF60E8F3D, &h1A41749B, &hF34C9F74, &h398060BF
Data &h54A9D452, &h323AC6B5, &hB2D175DD, &hEC860317, &h67B7A945, &h5AB43820
Data &hC835D2C6, &h989F8DC5, &hC6852481, &h4FF0E3FA, &h37CEA723, &h8637F457
Data &hC2A8344D, &h4FF9DEFD, &h3B11670A, &hF3F7B387, &h0995CA16, &h409AFD75
Data &h615D9F83, &hA8AEE40F, &hB5A3ADE4, &h6A5C57EC, &h1EF13934, &hBE80618D
Data &h69F9BABC, &hE4FE60B9, &h44768CEF, &h3B4966D8, &hA5750AFC, &h17369261
Data &h13B01F00, &h0F284E1C, &h09A4BEEE, &hA949F9BE, &h7188D7ED, &h2DFB9FBC
Data &hCC851637, &h06E42D3A, &h641DF194, &hA3060EE1, &hD2B08488, &hB58FB73E
Data &hB5A53E36, &hB4CDC82C, &hDD1F6035, &h4AACAE23, &h8751A32E, &hCE21C345
Data &h76A539A1, &hA42A3700, &h626287C8, &h6D0FDDA5, &h34A0EC25, &h0BC12356
Data &h287FA628, &h0CE21B7F, &hB2E32494, &h83BB55CB, &hCFB8FE4E, &hAE27E26D
Data &hA9914DA8, &h2257AE23, &h075AE7D4, &h8A899F11, &h8CF61BD8, &hD7365B93
Data &h33EEE2FC, &hAC9D5B4D, &h5FEEFB5D, &h81DAA04F, &h141422B1, &h7BAA055D
Data &h2734B6BA, &h321D84E5, &h110E37BB, &h9C897FDE, &hB869172E, &hD463B2BD
Data &h4FBDB41A, &h9B8060DB, &h35636D2C, &h9781D318, &h096078B5, &h00070AE8
Data &h0957F475, &hD846FBA9, &hF41306D0, &h406997E0, &h633BB551, &h7A8F86F6
Data &hA5539E2D, &h4C6F5B75, &h63AF9DA0, &h62606758, &h9C46551D, &h8C714EEB
Data &h64CEF2F4, &h7749086E, &h93C030B7, &h996BC372, &h3CE1B2E1, &h168960F3
Data &h1E655342, &h64B56A73, &h5FC08FF0, &hC96EA054, &h751EE113, &hC0F81B20
Data &h21D21F15, &h15CC4003, &hF630375B, &h18A391DD, &h7191735E, &hAF6E01B1
Data &h83F2E10F, &hC88773FD, &h581CFF8B, &hABD7C5C1, &h45B1767B, &h8429716D
Data &hC0668CD2, &hA639F1E7, &h956DE15E, &h7DF5F4D8, &hBE9F3BBB, &hE1439943
Data &h24CF2CE2, &h4272A7C2, &h6403DA53, &hF5A025B1, &h8887B734, &hD4DFFC43
Data &h2F35DAA0, &h6BEEE85A, &h347512B6, &hA05687CE, &h8B7D7F51, &hAD45EDC5
Data &h23C7FDBE, &hDABAA0E8, &h6A5C0D04, &h2BFB1D79, &h7B8993A1, &h6A4A0B31
Data &hD5F65557, &h9BA09A2C, &hCFF563FF, &h89537AF1, &h97CF0CD4, &hD23AD4B8
Data &h9E939B2F, &hC67D659F, &hF73CC531, &hDC49F6B1, &h9CE61F56, &h32D3841C
Data &h7AFCCA53, &hA875BF65, &h96FE6518, &hE3A58EB8, &h783F363B, &h8D13F008
Data &h47AB9CC4, &h5A8D47F7, &h8EF13412, &h05DCEA87, &hA06107D6, &h8D8D54B5
Data &h868CB8A3, &h0791DA39, &hB8828685, &h51CEC89E, &h3A50AA42, &hD6DE03F0
Data &h09C4EE0B, &h69C9A980, &h5BB9EADF, &h0060AC1C, &h1E6087FF, &h465210CF
Data &h18F48469, &h386A7028, &hA418EAA2, &hA8B6BF67, &h2D51378A, &hBECFC833
Data &hBD8F0BFE, &h9E873244, &hADD18FC7, &h503E3E63, &h71B6D476, &hC05E799A
Data &h69B16D65, &hA8026B83, &h9421B45A, &h9EB37E1F, &h9452B208, &hA289561B
Data &hF1EDBCD1, &hE72E9A0A, &hC84F6296, &hFA1DF876, &hE9131494, &h09A8C944
Data &hBC76370B, &hE3F925E8, &hB2FA7B20, &h75EB1A34, &hA9EEA4AB, &h4D986247
Data &hF957DC2F, &h9EFC37C3, &h13ADEEB3, &hBCD18399, &hEB8B3F50, &h4159C6CA
Data &h4AEB0989, &h346CD356, &h8ADD8B95, &h65C648C9, &hF54C1BE1, &h58A24CC7
Data &hB75B18B1, &h692EAF1E, &hDFEB6AE1, &hB519896C, &h05EAE012, &h18D69F40
Data &hF152F825, &h44AE0EA5, &h2F2C092C, &hD464391F, &hFC401CEB, &h3E0C4202
Data &h31EC460B, &h1689EA00, &hE7BE0163, &h6935B663, &h1A9F482E, &h168A91ED
Data &h29EB0168, &h33A32AFC, &h7710533A, &hD1B7CEBF, &h2E7C8F39, &hF6AADC27
Data &hB49B498D, &hF8E3C234, &hA3925565, &h82ABF7BA, &h4810B43F, &h0EFA054B
Data &h134476D3, &h4983218C, &h004920F2, &h8FFB24AF, &h5E9BA9D6, &hCDF34094
Data &h19FA0232, &h0901ED2F, &hF9B43A03, &hB7D580BC, &h144F9343, &hF7943944
Data &h14305FA7, &h70799847, &h0DA3E809, &hA83D3EB2, &h281BF2B0, &hEEF75287
Data &hCB852076, &hC557BB91, &h9642B1AC, &h71D875A0, &h6476B505, &h927B9412
Data &hEBCDCEAA, &hF41A766A, &hFBD7D63E, &h8D3FA5F7, &h309F74D0, &h1C5C3918
Data &hC87AA7F5, &h878EE879, &hE8C3115E, &hDCC09976, &h4E2F24A8, &h16C61E42
Data &hC0BC7E0E, &h76565671, &hE9039600, &h27E76617, &h3E9EC5DE, &h4D5BBF1C
Data &h78B62C88, &hCCC390D9, &hEC92066C, &hB73788BA, &hC57DA88A, &h393816F7
Data &h433FFA33, &h4DD6D510, &h1EB5A7C0, &h1B2CE7DB, &h48511B22, &hAFEEF430
Data &h9DDC3ACA, &hFFE04402, &h4C0EC265, &h2D9F277A, &h412EBD35, &hD11D1A2B
Data &h8256CD39, &h3096EA15, &h9AABE977, &h8C1DD3B9, &h532D1591, &h438F6C98
Data &h9DA4E7A3, &h2B1A39BF, &hB9420B78, &hF691700E, &hA15ADEC7, &h74B55C72
Data &hB1CE5694, &h60C8214A, &h5176402C, &hBA4B2993, &h5EDC83A1, &hA4551269
Data &h19F16E26, &hBA9B35F2, &hA5FDD2EC, &hAC972B60, &hC8F6AEB5, &hE1D697E5
Data &hB43623FD, &h2DF0D436, &h2CF9485C, &h143CF3CB, &h0F3A1B25, &hAC458823
Data &hB0BAA8DA, &hC3287475, &h420EE820, &hDB0DF39A, &h2FB914A5, &h4E596E4B
Data &hF7692D9B, &hF3D2E84D, &hF0BFE3F4, &h15682B50, &hA20EE915, &h0819B242
Data &h45BFB7BF, &hF5BA97E7, &h93D0A336, &h102F0DE3, &hD7349896, &hD0256351
Data &hDEA63C23, &h282FC0BC, &hB47C9F88, &h6F48563B, &h6649F3A4, &h77867C5B
Data &h19A5C4DF, &hA42988A6, &hC32D7680, &h18828B9C, &h2C34F32F, &hF1C55069
Data &h8339D6F5, &h770582A3, &h2F72579D, &h35F25630, &hBA615BBF, &h1D6684E0
Data &hEA42008E, &hF67C38A7, &h4CC54157, &hB5CA556D, &hBE2CC419, &hE332C750
Data &hFFB05EF8, &h7B78B819, &h480155C8, &h0D6C071A, &h6FC9909C, &h9A95936A
Data &h2ABD5B3C, &hB9757071, &h5014F1A0, &h831E3664, &hBD4D0E43, &hD658E96F
Data &h22A107D4, &h24ABDC43, &hB9894B2B, &h4D3914E3, &hB6286139, &hE0BACBA9
Data &h85F2272A, &h0944D90B, &hA92D8DCD, &hC64A7E16, &hADF81977, &h929AF7E9
Data &hCB528466, &h86581BB0, &h5B36C1FA, &h16B3C4C3, &hA8C8DDE3, &hB5396F31
Data &h0B211747, &h23FB52F0, &h240B40AF, &h2B213AD0, &hB35FF1A1, &h8FB5E18F
Data &h08616D70, &h46A06A61, &hC9AC3594, &h98FF5B69, &hA551905B, &h09858EE7
Data &hE69F0AF3, &hA4F6EA37, &h8FF94435, &hEEBC47A1, &hDB68074E, &h26AC5BAB
Data &h1E8DC7F7, &h9EE4069E, &hC6916125, &h1659B03B, &hC662050C, &hE2219F7B
Data &h0EC32277, &h807C4D61, &h58C86625, &hBC6A9C9A, &h40E8779D, &h3A3D1E78
Data &h47F30AE1, &h051C3290, &h8D780D72, &h940D4541, &hE1892578, &h5ABCDABC
Data &hB780AF48, &h1FE0BE91, &h95754530, &hDA1023E3, &h69CAFC2D, &h62775F91
Data &hC56FBE23, &hB777C333, &h8B011D0A, &hBB8ED1DA, &h9F533EAE, &h17B4D04D
Data &hA7845125, &hF4E2A0F9, &hC23E474F, &hE5E9D399, &hFF96FE08, &hE90A9590
Data &h112C4283, &hDF096C7D, &h3603A60E, &hD627EAF3, &h03219B14, &hDAA98491
Data &h55838A44, &h31EE86E8, &hF96E20F8, &hE38D46E2, &hD271FE13, &h60CDE81C
Data &h86A5162F, &h4F5974A4, &hE21BC64B, &hF3264181, &h70103DE9, &hE3D85FD5
Data &h00156501, &h2EF7183A, &h521CB7CC, &hCA98B2E6, &h14641A0C, &h4BB62388
Data &h6325D04C, &h8BA3E97C, &hFC71AA3F, &h912CFE5B, &h3BC81804, &h4B66928B
Data &h6F14577B, &h205F2A19, &hFF6B5CE1, &hD23D36E9, &h162306D0, &h844512FA
Data &hFC30718D, &h50D333A6, &h695D0358, &hA9395EAC, &hDB2451AB, &hE5A8AE67
Data &h88F81ADB, &h70E05F21, &h780CCE21, &hE076D9D2, &h88DAD13F, &h866A5251
Data &h39728FB4, &h3EC3FA3F, &hFB46EC0D, &h5EFC1CB7, &h62A82763, &hE464C342
Data &h86587B96, &h28E2C486, &h37024B04, &hD554FF3D, &h99E71F78, &h2DAB9E4B
Data &hBEE1D7C4, &h1366D5CF, &hBD1317C5, &hDD4D742A, &hC94F8C7C, &h16738E5B
Data &h56860978, &h4E821B94, &h1713AA42, &hF0FE028D, &hB14FD08C, &h4EE6904F
Data &h59C3BB90, &h98EC8AD6, &hB50E6878, &h9E805918, &h49020E1D, &h98FFD1B3
Data &hEEEFC439, &h6A941327, &hC97D7EA5, &h4DA3ADC6, &hCBDCEB7B, &hA3644A87
Data &h3B6C1FA9, &hCEA3FC7C, &hA865C06B, &hA6566A61, &h4E99C7AC, &hA83FB8ED
Data &h6F91939A, &h46DD6038, &hCA4F018A, &h9322E6FB, &h2D88DA23, &hA0898732
Data &h7CE45277, &h68FF48AA, &hC3903173, &hD8C4FEE8, &h3678429E, &hECB2C737
Data &hBF6A0939, &h7AD8AC2E, &hAA6855BE, &hD6E76BF7, &h743304DA, &h31C9EAE0
Data &h0A6C02F4, &h45C04E9F, &hB538B2AE, &h92B0BCB5, &hEFDB6FFD, &h02601138
Data &hEF458BF1, &h6DA276F4, &hDF649A55, &h872FEBAA, &hF74AFB77, &h8D02870E
Data &h7B704F3D, &h6F77266F, &hC8C36C0A, &hF11AF179, &h3DD18262, &h5E550D48
Data &hF9E0C231, &h79C17244, &hED6FA054, &h071B46FE, &h4E6DDE2E, &hDEA292B8
Data &h4B106D73, &h06198690, &h7303C213, &h07BF66DA, &h5BAF23FC, &h172E88E7
Data &h014D8A5B, &h05790316, &hCBCBEC84, &hDCF5EC6D, &h7344AAA8, &h03B4AC4F
Data &hCE14C828, &h5806B343, &h80736FF0, &h4BFE9308, &h3702CF28, &h1F4674FC
Data &hFE7D687C, &h224563D1, &h8755C2DA, &hFC590E37, &h111CBDBA, &h8BCEA19E
Data &h9E72DDDA, &h12D2E3A5, &hB88D9BA5, &hE7815033, &hF4FF1C90, &hE3E79FA9
Data &h05695FBA, &hF7D9D3B4, &hE28D82B5, &h555BE64A, &h58FEF5E9, &h0B2567C6
Data &h35DFCD71, &h8ACF81CB, &h00038FAF, &hAE0E25FB, &h44CFCEDD, &h88A2E647
Data &hFE2CFEC7, &h95967E20, &h80620161, &hF0A800EF, &h35AC0600, &h2C5F50EF
Data &h8B214584, &h7B576FC0, &h1E37C854, &hC08D08F7, &h7C17E62B, &h9A9CE569
Data &h95A0B6A9, &hFDCB1655, &hA4566BC1, &h587867FE, &h388E0F03, &h31123D1A
Data &h25D01BBD, &h97175349, &hEEE83AD0, &h0C1203F7, &hFC13A9E3, &h8EFECA6E
Data &hAE5971D6, &hAB16819B, &h5FDAC041, &h2E21EBA4, &hE387DE1C, &h141906A1
Data &h8B6B685C, &hFE72D70A, &h9CAD5F05, &hC1ABBC91, &h2F3E0FB4, &h808AB9BB
Data &hCEA7FBD3, &h20D82C60, &h8730D1A7, &h9D7003E1, &h3B70A01A, &hB763020D
Data &hD7BA075C, &h2162426F, &h0D056EAC, &h4B43D960, &hD2BFAA58, &h472F2F69
Data &hF2C43E9C, &h7669AD65, &h5D1AB795, &h70E1610F, &hCDFD040B, &hF704E88C
Data &h4C76E4C9, &h42ADC15C, &hC1E1AA54, &hACCA1AE3, &hEC3B29D3, &h03E857E6
Data &h05A62E36, &hDDE8C870, &hDA8D612F, &h89E1D665, &hF10D0E8A, &h5B331C35
Data &hC58E5C41, &hCBCC2958, &h2AF6A28B, &hB036793C, &hC1FE9EEE, &h78CD6415
Data &h92EF0617, &hBD65961B, &h7F3E3200, &h08AA1B32, &hFD05B26A, &hEED66957
Data &h9FA49BCC, &h120057AF, &h5FA82F92, &h2C31B8BF, &h5FE797C3, &hB0742993
Data &hF6E0E064, &h6D8E2313, &h6FCD2E94, &hEFA3AE83, &hB5B244B1, &hEE18A8BE
Data &h9B4635D0, &hDA0F5CA2, &h927E9297, &h5A829A95, &h2C5AEC38, &h1BB80880
Data &h6812FCC2, &hFBA368F4, &h415B29F7, &h1DC65821, &hD559DBC6, &h33B3097B
Data &h8A20F529, &h8EAA8DB3, &h13C09808, &h13B066E4, &h08BD534F, &hC33B2AA2
Data &hC1F58187, &h91A4CE13, &hB9A51E82, &h3F74DFA5, &h0524E4AC, &h28C1F8D1
Data &h3DA4C369, &h94AB2713, &h3A2A3F49, &hD0A30EFD, &hE3FAD7AE, &h401196C2
Data &hE43AA073, &hCAF8ED36, &h5F876A01, &hFFBBFF07, &hB5ED5745, &h64F1A6D3
Data &h54F82B24, &h3F90839D, &hE7F19929, &hEB024EDB, &h15BCFD30, &hD18FFED3
Data &h566D5D4B, &h01048018, &hCB4BFF75, &hCD7A4C8D, &h489D8BFE, &h29C392FC
Data &h7842264D, &h22EE8CB7, &h709B42E3, &hB3A99B10, &h4C03CC08, &h21F6EF40
Data &hAE3FBC7B, &h98F65D03, &h16A4A378, &h09B10553, &hD229A223, &hE0A76ADB
Data &h61607C88, &hFDA1DAE3, &hB37CDCD4, &h3A7C8F0F, &h927915B7, &h01B6F174
Data &hCCC5D68F, &h8B3434FF, &h33870EC9, &h7E2FEDB8, &h28970D3E, &h50976BE7
Data &hC6C9A3C0, &h697ADFF1, &hCD4CBFCA, &h9F2C098E, &h5B595301, &h2CFA36EB
Data &h7980173C, &h9D84FFCD, &hDCA15A43, &h67432904, &h4B6990D9, &h7B7F959A
Data &h9807DD27, &h6340A052, &h5164CAE1, &hC212040A, &hB8405C09, &h02E849FA
Data &h1911B4F2, &hE9933102, &hEA1EEA36, &hBD807ACA, &hEFFB20A4, &hCA0AD5D2
Data &hAF1EDE4E, &hF215535D, &h26A9E68A, &hF626396B, &h04841C30, &h73CCBA73
Data &h02F60B39, &h5527E632, &h28FB43EC, &hA3528922, &h7DCE4283, &h5E49F85D
Data &hEF469626, &h4D850EBD, &hC1FF688F, &h80696A6B, &hD7404978, &h558A1005
Data &hE98AA0C4, &hA303A3DE, &h35EE9806, &h1C30A804, &hCFC237EC, &h0A17FF8B
Data &h62F88A77, &hB3A659E4, &h46158322, &hC2776B44, &h2D8A2252, &hAC03F929
Data &hFE2B1F62, &h277B2B2F, &h3C183E4D, &h89196FD3, &hCD7DDCB6, &hD47BBA77
Data &hF700721C, &h7C0BAF46, &h44E4CB2C, &h6152B666, &h6AED53F1, &hD9E042F6
Data &h56F6678D, &hC82FF4E2, &hB1B2EC5D, &hBFF87A9B, &h70F3C4D7, &h13872AA3
Data &h6C9C4335, &h35908E3D, &h5B970A92, &h70691F08, &h0055C556, &hC768566D
Data &h3F11FF52, &h539577A0, &h2E417936, &h9694E45E, &h00CEF93B, &h21C90708
Data &hA67AE7EA, &h0FA90540, &h663D731A, &h81B11A50, &h5036905A, &h5D802432
Data &hC02EB3FD, &h1D014DC6, &h33A419D4, &h075EB6B6, &h81B56E79, &h71811F60
Data &h24D629B1, &hB416D4D5, &hD3CCA047, &h4595B776, &h75E30C31, &hF8DF48C1
Data &h0F568EB5, &hD3CA3012, &hE466581E, &h95AD4944, &h48CC9158, &hDD91207E
Data &h331E0DC2, &hD35E4276, &h5A8BA372, &h84DF74F1, &h1DDFA358, &hB5C740B5
Data &h248D0D6A, &h119CA3AF, &h91F65674, &h37AB4032, &hA6DDE7E8, &h805482D2
Data &h65E97F8D, &hD2A1A3DE, &h7BB6E8E2, &h4D6A1063, &h04FE463D, &hE36A1675
Data &h760F83CA, &hB34BD564, &hC6F84E39, &hEE0D8A3B, &hDD720C8F, &h7735E973
Data &h94AA3AF9, &hC1074FA1, &h16F7EC56, &h82ACFD77, &h8B173924, &h72E53A38
Data &h2B6786B0, &hC85E104F, &hFB25C5F8, &hFDD77215, &hA21EB1C8, &hF7C2811B
Data &h09CEC4CB, &h57F14A73, &h167670F1, &h46D913DA, &h75113F76, &hF3CD41AA
Data &h809FC188, &hCA2BC2F9, &h916C894B, &h03E110EB, &hDE88B70E, &h0002F452
Data &h7E169C42, &h686FF496, &h8519B2AA, &h2651A53F, &hFF21AF58, &hA6D12129
Data &h885CE8D1, &hFB413B30, &h0CDEFC2B, &hDF90B50B, &h46E7A084, &hAB93BD5E
Data &h520FDA09, &hDF828DF7, &h1745B331, &hEBEB2BE2, &h13A5F6B1, &hA3B0B3F8
Data &h2DB7CB2B, &h2CC60066, &h40A85E05, &h18D4BC1E, &h7FCB6274, &hA646A0CA
Data &h98CB4B1A, &hC2DDF54F, &h860E7B8B, &h10E98E4F, &h8F0E0492, &h98875383
Data &h142DC403, &hB0F98D2F, &hBC03504E, &h22AF3C53, &hCF36FC2D, &h2CD62944
Data &hABEBA979, &hB2E5FFDA, &hDBF0FCCD, &h038EBBFB, &hD605555E, &h6C6FD8B6
Data &hD4D29688, &h2A47C4CD, &hDC685EB4, &hB203E4E1, &h4E8627BF, &h16FE815E
Data &h271571D3, &hC21EABD1, &h8D860AA8, &h2DCA3503, &h541369D5, &hB217F9AF
Data &h4764B05B, &h15C81E20, &h7369F3DD, &h0253D11B, &h3DD11DF1, &h7608EAE8
Data &h2DEED244, &hD59BEA94, &h6736FBEE, &hC915330E, &hF0A0BA4D, &h8D3CA5DA
Data &h5F50CF7F, &h4D402010, &hE0136007, &hE6D9B755, &h5DEFC24B, &hFDDEB192
Data &h337C0D9B, &h3AF3F178, &h30519512, &h778AF4D8, &h78D77DD6, &h5AA1BB48
Data &hC302345E, &h4B78C8B1, &hA71E34AC, &h5EE4DAFF, &hA959A755, &h00105185
Data &h8468EDEE, &hC1734652, &h0CF53415, &hE9C87F56, &h39CD9A9E, &h54D4BAF7
Data &hBF1F0879, &h8CED849D, &hE55E15E1, &h4EB25FBF, &h4188BEBA, &hAC174017
Data &h3D1AEE5B, &h24F832F6, &h40F92508, &h726B75BA, &hA702FB11, &hA000F1E5
Data &h6E78AC99, &h743AE297, &hC413E3B1, &h51CD9C27, &h4ACE0A75, &h941854C7
Data &h2CEA6965, &h3A4A4FA6, &h9B66B12F, &h838FB7C5, &h57B31DF8, &h22A64A4C
Data &h7A6BB579, &hD12524DD, &h2EF9AFFE, &hCC586971, &h8261DC57, &h748E4FFF
Data &hBCBB1BD5, &h6C91C6BC, &h684A03DD, &h6C34E416, &h7789DF5B, &h7DE5AB7B
Data &h55EC1A02, &h7A77E5BC, &h80F5D73B, &hF57343E3, &h2A9C8781, &h6AA4905B
Data &h48DAFA82, &h6786CBD2, &h33CB2D8E, &hC247C60F, &hB176E0BF, &hCFC90055
Data &h803FEF6F, &h8D4B533D, &h882D4681, &h05E540EB, &h6B5AE56A, &h129A7FD0
Data &hDDF8C5D4, &h1F5FBC75, &hB10AE669, &h5DD81301, &h569FC1B3, &h9DFB2C89
Data &h5379F95B, &h58CD8556, &h13B6F3D0, &h443368B5, &h674F5CA0, &hA47F62FE
Data &h64B740E5, &hD4E969DE, &h58B1D3E0, &h772AD31D, &h0CD75B2C, &hEC85F28A
Data &h727839A8, &hA5338ADD, &hD03C67E0, &h904D6B17, &h0D6F0FBB, &hE7E69329
Data &h487DF3A4, &h571C2497, &h61B924F5, &h4F8DAA47, &h18417C99, &hE405063D
Data &h6B42B9A7, &h8B0A0D72, &hCED5A44B, &h92F44DB1, &hFF9E8E73, &hAA85995F
Data &h65B6B465, &h98271D54, &h22B2F497, &hA3B9EA1A, &hA892BA1C, &hD6F6A99D
Data &hB4B5F4A3, &hFC9C8249, &hC451B743, &h507AAFDE, &h52986915, &h583C6AB9
Data &h22A58C06, &h9434E6DC, &h1E61163B, &hC0C43975, &h331B2F86, &h05A01940
Data &h869F266F, &hFF771B89, &h4412378B, &h27730847, &h4ECEEB73, &h82DA9C60
Data &hDEF1D4FC, &hF9CC5CD9, &hD17961DD, &hFFA43A39, &hCF8BD77B, &h547EDDD5
Data &hFDE97649, &h427B50C3, &h39265031, &hC0DF8428, &h718E149D, &h9CC123C8
Data &hE036BD84, &h1F704936, &h73378EF3, &h34DABF10, &h4055ABAD, &h81A2B466
Data &hBC4DD776, &h89BE2096, &h7434D100, &h19F09157, &h2F0C7708, &h19A4988B
Data &h988049C4, &h07AADF71, &h1A6D9510, &h0D5D5246, &h6D2B34B2, &h43B168EF
Data &h5CE1086F, &h63F84241, &h2CF61749, &h68BBE376, &hB0E39CAF, &h62D1DAF6
Data &h840D8953, &hDA3B3582, &hAD20A3EC, &h9EA75087, &h3FCA0B9F, &h7CFF8F59
Data &h47176342, &h81616B26, &h7494CFD3, &hD14E262B, &h0A3976D8, &hE658536D
Data &h5B25139A, &h6F8CD780, &hD6822885, &hC50842A7, &hBFCF1BA7, &hCCD948F1
Data &hC3ADCFAE, &h8779A927, &h2A6DF5AB, &hF2471E69, &hA98D3F4E, &h2730B3DB
Data &h530AFE96, &hBDD5E87C, &hFEEDD917, &hF9C2B1EA, &hBA4C2B28, &hD2CF1223
Data &hBCE953A6, &hABD20B1D, &hE712DC9C, &h61BB7FA9, &h34B906D1, &hE9FA2E53
Data &h567D882A, &h40400B6D, &hEA36D61A, &h7DDC5A97, &h1DB9F190, &hEA9448A5
Data &h0C26A7B9, &h685139AF, &hA860A46D, &h5CCCE921, &hADCEE46E, &h27D79DC6
Data &hABE06E17, &hC9D8C749, &hA0F54529, &h63F150C2, &h0737BF24, &h14406919
Data &h0513F74D, &hE53AD5F7, &hCE2E8BEC, &h0B738451, &hE8C010F9, &h501A2F3E
Data &h04942AE5, &hD8B68EB6, &h98FA5487, &hF52BAA1E, &h618C7157, &hEF43C04E
Data &hF3B98CF9, &h9DC4E15C, &h6F378F52, &h7FBDC7D3, &hE9EC92FA, &h106F367F
Data &h6C5CB3FD, &h9B4B2DA2, &h621EC8F5, &h01E99283, &h928659E2, &h2D2FE91B
Data &h2BCD4D01, &hFD546672, &h22A9E12B, &h7FF3B865, &h5D7C7EF6, &h7A91C540
Data &h88FC5EDC, &hEE3B5605, &hC87A70D4, &h9C3EF667, &hF368DE77, &h7392A50E
Data &h5CB5A678, &h0D5FFD19, &hB62C2A76, &h4C44FD2E, &h178F4988, &h38678039
Data &hFDB72BC7, &h1692283B, &h8C704FC3, &hF39AE392, &hFD92E748, &h7EEABA74
Data &h7890C9FB, &hC10C6E7A, &hEA839464, &hC8967827, &hC907BDBD, &hACB7DD6C
Data &hA9209E2E, &hA319B990, &h30FA4E79, &h895C9CDD, &hF9EE0BE6, &h255A98D8
Data &h5FCF08FF, &hCA7A18D6, &hC60B9338, &hFE6E6C19, &h30FDDED6, &h69543BCD
Data &h0EFF9B50, &h15F8DDDC, &h52635EAC, &h7194EA83, &h0AB5FC2B, &h939CF7D2
Data &hED006102, &hE67ED358, &h3FACCB80, &hEDC45B53, &h273D53C7, &h8C9871E3
Data &hC577E067, &hB48AE64B, &h309068F8, &h3F87279B, &h1DACB19F, &h82CBC70B
Data &h0DE7DD81, &h5FF9C372, &hFDD5D876, &h10A6A34F, &h6E80104B, &hD7C95474
Data &hE4A03886, &hF01009C0, &hCD695DB2, &hE6FBADE8, &h233BD197, &h09D971E6
Data &h46832E72, &h6E243C48, &hAEC19587, &h27BBF512, &h5C2E9653, &hE03B5184
Data &h7FDFB597, &hB24598CB, &hF1087732, &h18E663BE, &hD77B9BA1, &h08853822
Data &hC02C574F, &hDB9193C3, &hA2A99809, &h6636ABAC, &h37092B0D, &h54564FA6
Data &h6A1D7C4D, &h33E131DC, &h7254ED19, &h422F1F3F, &h134E1075, &h90A73181
Data &h47D72ECA, &h1FF903CA, &hBA763A38, &h1E95D28C, &hA49B3742, &hE097D734
Data &h9AE249A4, &h5DDF2FC0, &hB5D685AD, &h4DBA3BC6, &h97267E36, &h18376AF2
Data &h42FF536C, &h9C1079F7, &h1EC8759F, &h812CC2A8, &h349E485C, &h73CB1F04
Data &h774C2930, &h18956924, &h67A2990B, &h8206B54F, &hCBCF945D, &h2E57B0AC
Data &h323306B1, &h7C7D4534, &hAEE4381E, &h688D9F4C, &hA6CD15A8, &h0CF6D1BA
Data &h9819E15C, &h723C2D92, &hDBF8AC5D, &hF86AD381, &hEFBD3C50, &hE9964D76
Data &h8711471A, &h28AA8E2B, &hD4365D82, &h63B2FE58, &hD5135AB0, &h03A68D53
Data &h53CFAF52, &h3C77974E, &h988EF97E, &hF645E42F, &h26559290, &h3784FD6A
Data &h264EFF1E, &h99CC186B, &hF4DEDD24, &hA1AAFF09, &h984146AF, &h54B133C8
Data &hF43BC724, &h5419DD69, &hA9BDFF10, &h71F39DA8, &h5E978DD6, &h03852322
Data &hC24E888C, &h66F64010, &h0C0BCE23, &hF8380020, &hAE18ED84, &h6EFE9261
Data &h1FDCB6F4, &h43B6CABE, &hD0F9D13A, &h93E427CF, &hA05BC4F0, &h8B81C53F
Data &hE7200102, &h15F37C51, &h0608621F, &hC5BA9C34, &h25C022F2, &h22C7B454
Data &h438AD92F, &hF8E10339, &h51C92C9A, &h7CC2927D, &hEA8618A9, &h83A1701A
Data &h69A2474B, &hDDB85E40, &h92069BED, &h4343767B, &h3EBF3592, &hE049A713
Data &hE5490AD7, &hBCF24498, &hEE87AE4B, &h0186F347, &h75F7371A, &hA1082DA2
Data &h0BA09B25, &hB82D322D, &h59046DA7, &h4A4F1DCA, &hF7D51F72, &h38DD5981
Data &hACA3FBA2, &h67B0F288, &h5605EC58, &hB2BAF169, &hD4F7CF6A, &h54B65E99
Data &h4663BCFC, &hF00B1110, &h69F6AA0E, &h82BFE638, &hA987B710, &h5490D4FE
Data &h3A508C7B, &hE2D31F81, &h0424A627, &hEC0F32A6, &h6D9657C1, &h661F611B
Data &hFD84E9C1, &h1B36AC74, &h44677450, &h4B1D51DD, &h5790A1C1, &h638D0932
Data &hDF878D22, &hCC3A1318, &h9DADCDB9, &h311D1C74, &hB5A81172, &h05804F91
Data &h5EA879DF, &hB86E9F88, &hAC1BB525, &hFF090BCE, &h3E26714F, &hAEEAEABD
Data &hA7F9CD71, &h83BC6B65, &h670330CD, &h955CE723, &h3163D1DD, &hC9D5E75C
Data &hCB33BBAA, &h909E75FF, &h121B9EB5, &h077A37DC, &hA77D1281, &hA3154C7E
Data &h879FD982, &h2EA1AF3F, &h28255DD8, &h47FC7C7A, &hE3DEE629, &hB97D9A24
Data &hB2331C74, &h44099BAA, &h7D30CF10, &hB6D03490, &h188269D7, &hC39C8633
Data &h8C20DF6F, &hCC3A2C90, &h1EE03195, &h8DAAA653, &hBBBAE03D, &hC35AF97E
Data &hACA4BA73, &hE42FD876, &h28AC9D94, &h03C51203, &h56064375, &h0E8F3003
Data &hCE468913, &hB13392DF, &hD0890C9A, &hE284B5A7, &hCEA88D64, &hC4EC6BAA
Data &h3EDD1110, &hD84371F7, &h3D7326F9, &h2C65CC11, &hEB43D69E, &h4E955689
Data &h09861BF5, &h2E3E0A37, &h5BCDCCFB, &h7EC98A9E, &h2DEB5BAA, &hC10EA34E
Data &h5E36CE71, &h2ECB8C62, &h4D883B6C, &h11ECFE02, &h03ED7F82, &hBD1C61B6
Data &hBD348217, &hBD64010A, &hA6090B43, &hEEB5978B, &h7A3AF90B, &hE7898B79
Data &hBBC9056C, &hEC1F25BF, &h07F21410, &h25DA5502, &hD284D243, &h2FE97CC4
Data &h19AB82C4, &h86F1A68C, &h19A795D0, &h0883DE94, &h8B4A1362, &hBBF55D7D
Data &h0BF8C7AC, &hB102F018, &h18AFB80D, &hE6642919, &h1A02B9DF, &hD589C6B2
Data &h5F501A7E, &h8E4B8246, &hED556039, &hF1DFAA0C, &h9294E800, &h5CCC768B
Data &h0B42DE64, &h41F15F14, &hC57F5AB6, &h823DBAAD, &h491D195A, &h2265E505
Data &hD4D86A11, &hBE0F9603, &h2A0B412B, &h7FCA20BA, &hCAC29EDF, &hAC78255C
Data &h9195BE17, &h7F60AA76, &h22A3439C, &h981DDBF0, &h5BD021ED, &hAEDDABCA
Data &hE55B9743, &h97FC5698, &h1C927CB1, &h04B9966B, &hF4AE8643, &hC8B22184
Data &h52EE7914, &h514E9A80, &h7317A070, &h72C78253, &hD44BCBAF, &hFF4656E5
Data &hF087B2FA, &h895B82A7, &h69B59A35, &hD416364B, &h9455177F, &h4892D8FE
Data &h90AF15ED, &h9FA8313D, &h1D3263F5, &h2DC7BF76, &hBBE0A497, &h32B4F3F3
Data &hF45CA4E8, &hB4B05CFA, &h54A8C98E, &hF9B72C8A, &hDCE01CE2, &hCD35A159
Data &h0E26E430, &h10B8FA7B, &hABF7C1CA, &hF19ED4EE, &hB218523A, &hD2C4A427
Data &h9C838F14, &h2F055E8C, &h29541566, &hA299BF45, &hAEA6C4B6, &h9770C290
Data &hAA2F7DA1, &h366C6DB1, &h44F33D5A, &hC2830486, &hE3BEE44B, &h632BE254
Data &hB04A4B58, &h8FA0DA01, &hE442642A, &h749F1B7C, &h839413AB, &h69A7F7A5
Data &h944907C1, &hDD7807C3, &hC1081656, &h0424ABDA, &hA00C0BF0, &hD8CD76D0
Data &h153A782F, &hED871EC9, &h2B5F4E14, &h33AEB992, &hA173E14A, &hA8A6EBC0
Data &h2F64B92E, &h99B6CA1D, &hA22BE700, &h9CF060CF, &h0B4FFE66, &h1E80C830
Data &h13D32BC4, &hC0C78F3B, &h2341A7B1, &h5EED32FE, &hA922026C, &h878E7D24
Data &h81F08D37, &hEEF44953, &hB5779499, &h883856E3, &hEBE82CFC, &h6E5CA50B
Data &hCE0A5A8C, &h94BF352A, &h00AE0CF3, &hC912B573, &h4EB65FF0, &hBC69B51A
Data &h9AB29A98, &h4AF73629, &h7556B786, &h41C1D057, &h815B46D2, &h63D6241F
Data &hF57CF6CA, &h66EECB39, &hE3D58987, &hC8901FC9, &h94748A44, &h7EABFEEA
Data &hF554741A, &hBA2D3AE0, &h11AC0F75, &hDAC8DAAA, &h5170414B, &h4D44B539
Data &h9241C776, &h2E7BB0E5, &hD49868A0, &hD5CA184E, &hEBD30C4C, &h7FD3B0E0
Data &hAB0D249A, &h05678723, &h4496033F, &hA329FCE0, &h0BFDF3D2, &h34AF5B83
Data &h690E7999, &h3F3BF44B, &h3FBF193A, &h04357552, &hF24BE909, &h61157A6C
Data &hAB6D0A27, &h2E688FAD, &h3318F926, &h97589CA8, &h2EE8C720, &hC3FABD1B
Data &hFC8EA0B7, &h8590D98B, &h1B82C4FD, &h362E21AC, &h4D47EC20, &hF9AFDB43
Data &h41EBFD50, &h0770956C, &h4EEF6C0C, &h5C648871, &h4402290F, &h0225F378
Data &hF11D685E, &h8C36853D, &h32F3F88C, &hE1C039D8, &h89F05257, &h2EB34964
Data &h02CC054D, &hD258B657, &h46C2A7CC, &hA7F38B66, &h1F0B85CE, &h45296091
Data &hC9C6C03C, &h505F0935, &h2EB52028, &h601602C9, &h9299F749, &hB8C5EA15
Data &h1F8D33A4, &h2CA0D5FB, &h7F13FE63, &h7E01F9E1, &h2EFF5AA1, &h9949082B
Data &h0EBB7FAD, &hEB9AF0C9, &hB9AC1CCD, &h5B9F751C, &hC2582ADB, &h041F1CFE
Data &hE47D2D88, &h62E40B99, &h35CA8B43, &h9871B030, &h50F03310, &h1A8F2AE0
Data &h66803560, &h69CABEF0, &hCB5484BC, &hCE265A72, &hE05A2EE4, &h46187689
Data &h76EB7F9C, &h68B7E50B, &hD50A4AC2, &h44F9AFC3, &h20C1C64A, &h9F9214E5
Data &hB4B5EB33, &h077727DB, &h037DE862, &hEF91ECD2, &hD11279D1, &h5A1367E1
Data &h1DC4696E, &hD96E8539, &hDACAB85C, &h2FD31DE1, &h97BDD514, &hB18AA016
Data &h78382990, &h1ECD411F, &hD6A53FC3, &hF446065D, &h7969C563, &hFE925CC8
Data &h9B72EAD2, &hF38E635F, &h7790FF3C, &hE5162394, &h1390E59A, &hEA70C4E0
Data &h2130A4DF, &h5882FD39, &h32170738, &h8DE9D962, &h49C2BFF5, &h27A5557D
Data &hEC78E5D2, &h02854E53, &h3DC7D59F, &hFD06C732, &h4F1650DC, &h70C0BCAC
Data &h40F606E0, &h81FCCD45, &hF75EA047, &h9CAAA4F2, &h0EDBB391, &hDAFAFB03
Data &h4A1B2A8E, &h4B4A79E7, &hC43F2F61, &h0F37CD89, &h57156996, &hEBB9EC31
Data &hBD6FB69B, &hE40566F7, &h47F97AA3, &hB4259A05, &hDBDDB615, &hF12E179A
Data &hD1DD78CE, &hA2321851, &hE1409E06, &h20EF4DCE, &hDEEB7CFC, &h282A7052
Data &h59F05911, &h0697EB3B, &h280792A8, &hB00AC8D2, &hEE578455, &h32B1BE26
Data &h2F9849E6, &h11251792, &h221B8BEC, &hCC2D7903, &h139116E3, &h017ECCD0
Data &hB7C21646, &h0A655F65, &h91E09704, &hA6CFB7F2, &hF4ED147B, &h105D560E
Data &hEC7AF450, &h7881D805, &h3E21CFEE, &h263C36A8, &hBD2B44CA, &hF5C38D8F
Data &h568A1757, &hAC042FC0, &hAF2CD1DF, &h81BBA5FD, &h70B8DF54, &hEA0F8AA8
Data &h691EDD84, &hB049E8BC, &h9751F3A8, &hAF7F19ED, &h094A3250, &h6B539919
Data &hCB4BAFC7, &h73F36DF2, &h619931C6, &h525FE50A, &hD48F7FAE, &h4C2F547C
Data &hD87658E8, &h9002441F, &hB0388A03, &h1017764C, &h4BB76144, &h14E04ED2
Data &h9964A2B2, &h1BE58108, &h834CDD56, &hEFF0812F, &h20183F08, &hDD630A8C
Data &h3B071D45, &hA7363FC2, &hCE14FBBA, &hEC702FC3, &hD11139E8, &h2EFD5F84
Data &h675465BF, &h6B578646, &hC05EC201, &hAA6801F1, &h17377B4C, &h96CB01F0
Data &hFCF2F7FC, &h75774691, &h230D4CCB, &hCF4CA59F, &h67EABDC8, &hB2FD801D
Data &h2CB0719F, &hF32BB1E1, &h3998DB00, &h9E1F5303, &h5E4A3338, &hEB9D42B1
Data &h4916AD77, &h46D8A126, &hE1FDBF46, &h7E32D997, &hC10A7262, &hA20A0477
Data &h8682FF45, &h5BB4AE35, &h103D03E3, &h7E0BAA6B, &hA1D549B3, &h54DA4DCA
Data &h5604F58B, &hA7C1B19A, &hB7FBB8FA, &hFF8C280D, &h8205C8B9, &hB73E3E0C
Data &h4E429A96, &h329929C6, &h9D6A3656, &h36E99D2A, &hAAB66EAE, &hB6541AA8
Data &h271CFFBB, &h2A344461, &h2F2AF9AD, &h4CD5C378, &hCBD65F8E, &hB8EB71BA
Data &h900FA8ED, &h4A57E8E4, &hC52C6E52, &h1E9426F8, &h38814793, &h6B9510B7
Data &h4EB546AB, &hC83FCA4F, &h12F73BD8, &hE8AE6F6D, &hD9BCBD54, &h324F7DFA
Data &hC2AF71B4, &h237C21F9, &h8249E7E0, &h99786EDF, &h79D05767, &h7BA3E578
Data &h9A0026E6, &h19BAA025, &hA0012E14, &h10EF4D9D, &hAB4023CA, &h3C0BB4D6
Data &hBBC7C0E1, &h6E2AE76F, &hDCBDFDF7, &h80804215, &h632987B1, &h01F6BF4C
Data &h8E6D9F2B, &h2C2BECB2, &h992E5CB1, &h8EDD761E, &h7109698F, &h90900CFB
Data &h31989536, &hA4078E63, &h93975985, &h54F93CCC, &h669CFB56, &hE258B984
Data &hA5746D97, &hF4D63DD4, &h49F44907, &h1FFA48E8, &hD4B084F3, &hE979CB75
Data &h4BC973C0, &h82D3E564, &h86EAD806, &hA69A42F0, &h72812A17, &hB10C2850
Data &hB1AE07C4, &hA09AE092, &h66D88891, &h10414275, &h1A8AA593, &h180D2ADA
Data &h11B70D7F, &h5CFF5496, &h88BAA701, &h9C13B407, &h8BD00633, &h599D2051
Data &h415CD8A1, &h0C1386AA, &hB3C93D69, &hE321E0C7, &h1EEE0DF9, &h0A80EC95
Data &hF89873CA, &h4FAF67F2, &h39FA2D3E, &h3024309D, &hFBE8884B, &h76CBB7F1
Data &h0BCC93F6, &h23C3CF6D, &hA0F09512, &hE090EC75, &hB3E7AEF8, &h50C841DC
Data &hFCEC8211, &hDB1CA8EA, &h01D6AF03, &h29123583, &hD697D0C0, &h29DFB736
Data &hD89904E5, &h66D8A86C, &h2C2C9FC0, &h605E16C6, &h5FCA6D50, &h45F3D36C
Data &h92C0BC5A, &h3D5830C0, &h7370C3A9, &h414B29FB, &h1FBA9658, &h444198E0
Data &h2DA438B4, &h06374BB7, &h25469058, &hB05EB087, &h468436F2, &hF3FEE647
Data &hBC470661, &hD5DBCCEA, &h2D00483F, &h818A4BEB, &h4B95AA8C, &hF8051079
Data &h38A4A0CE, &hC470C246, &hF221F111, &hC7319076, &h4D6106B7, &h7DE8D1C4
Data &hE0FDD680, &h05252DE0, &h35BFB075, &h10426065, &hE1870B63, &hD659F239
Data &h6C3C0645, &hEE6F9718, &h87D72501, &hB4E70DEF, &hA659F1F9, &h70D7DAF5
Data &hDB79DB6C, &hCC797ACD, &h6F9F552C, &h5D594AB3, &h4740186B, &hC066573D
Data &hA280C79D, &h7CE05EE5, &hB086975E, &h153616F8, &h7327F3CE, &h4367A2BB
Data &h22AEBA32, &h6DBB992C, &hF8CFC4B9, &hADE7587D, &hFE583838, &h6A4CE8DA
Data &h3A6E3DE7, &hE84456B7, &h2F1CB537, &hEC112CB4, &h3C25CC73, &hD94EDA6F
Data &h27035524, &h4CB52FC6, &h24C93D61, &hE59DDF11, &hA897F275, &h8E88133B
Data &hF392B28E, &hD5E4D03D, &hC2F792D5, &h0A495E59, &h65494B67, &h2452CC46
Data &hA01B81F6, &h9CBB6C6D, &h0D3F495E, &hE26809C6, &h310F1139, &h7CB8032A
Data &h6152B51C, &hE91F8962, &h2253B1EA, &hF14FEF58, &h5AD57B37, &hF8AE6388
Data &hCECE0617, &h86C68139, &hFD411F43, &h07475C73, &h345CABE7, &h2F501CEA
Data &hBBECD5AC, &h90417874, &hAB3576A3, &h04D55D2B, &hAD824B80, &h92E90AED
Data &h0AA40AB3, &h0C06A6BD, &hC9665B21, &h5BE80EDA, &h205F885C, &hD236C674
Data &hA1C17473, &h05DAF7B0, &h7D8F19ED, &hDE72A8B5, &hCFC551E0, &h5B4693AE
Data &hF03267EA, &h119B8497, &h0D491207, &h34A97DE6, &h2E498BEA, &h539079E8
Data &h340FAA5F, &h7BA752BC, &hD76C3863, &h7FAEACFE, &h8C549877, &h5BB6C62F
Data &hC92407D1, &hCDCF6D52, &h11789168, &hD4559619, &h31A4AFD6, &h18D7C34C
Data &h0BAAC4CA, &h87F72CC1, &h642BAEAF, &h35F4D217, &h6D43B558, &h7C49A1E4
Data &h0714542F, &h449ABF8D, &hC1509033, &h9DE17AB5, &hD4B629C2, &h4E3E49ED
Data &h516E751A, &h134EEC82, &h651B9241, &hA458CE40, &hE5E6F799, &h3EE9FE9F
Data &h322ACE37, &h19176135, &hB50455F8, &h951C7700, &h89CA7953, &h927045BB
Data &hA2ABE9F3, &hD99CB3C9, &h466F2215, &h99CB831E, &h8C397EE3, &h619A5E10
Data &hB535552C, &h776F77D0, &h40862D50, &h503DA609, &h32E383CC, &h22AD4D91
Data &hDE128F70, &h98D5FEBA, &hF83E05D1, &hFDBAEA94, &hA54F2F19, &h428B05DC
Data &h3E1659D3, &h16BF406D, &hDF667814, &hC72B2197, &h932E9B6B, &h8414BD58
Data &hFB22D6B1, &h24331DCA, &h071DD740, &h53FA5086, &h14B04C55, &hE2CD357E
Data &h788DBEA8, &hADED5B1F, &hA059851D, &h0AFB4AB1, &hB25AA95B, &h97F09BA9
Data &hCAE90782, &hA6F569CC, &hD486FA33, &h12E90A0A, &h8F4A46ED, &h4ED25759
Data &hFF6763D9, &h6CC34A42, &hF1094A23, &h48F4B731, &h45CE28EB, &h7B685E0F
Data &h7B80E172, &h03282C4B, &hA5D607E1, &h2EBD7FCA, &h491BEADE, &h073C191A
Data &hC5A8C0D0, &h9F4E6C4F, &h9468D429, &h75E7344C, &h3646A128, &h64E7AC46
Data &h7D34FB81, &hAC202CEE, &h4C351337, &h651C6FA7, &hFA4B148B, &h82826CF4
Data &hC0B0902B, &h81275C40, &h0225A110, &h4EB1A967, &hBCBCC89C, &hD29C30B9
Data &hA6C6F3E7, &h99484763, &hBF257767, &h7C5BF312, &h193A5C33, &h14D516DE
Data &h56B83EDD, &hAFD52C07, &hEB8B6984, &h77AD739E, &hD31B86CC, &h9387B735
Data &h5C97060D, &hCB0933FC, &h3D1683FC, &hD90486B8, &hFDFFA787, &h3C70355E
Data &h367F3CA0, &h4D8A463F, &hB1C6B22B, &h1E690CA8, &hECFE2CFC, &hC077E6C2
Data &hDD5975BE, &h4F8B1A58, &h85F8AB95, &h94377294, &h4A1D1694, &hD457614F
Data &h8D5E0EE5, &h881CA554, &h0EC8BA48, &h380E546E, &hB42F06A1, &hB570511B
Data &h0895A49D, &h894D2250, &hD95AB962, &hD18D1257, &h93A4DFDA, &hE8C0C703
Data &h7E0FF4AC, &h3EC8AE29, &h90CAA73B, &h57FA801D, &h4097908A, &hAA1BA265
Data &h6DEC00B9, &h1FF14029, &h228C8EAB, &hDC723309, &h6ABD144D, &h192B7A1F
Data &hD6A35B7F, &hF13C0208, &h0F41C499, &h512AA7C8, &hAD14BEF9, &h990DC4D2
Data &hD8CF184E, &h4A380F9B, &h1C8635CB, &h13CB5CA4, &hFE91E938, &h8DAF2730
Data &h6F8981A0, &h3329CAEE, &h79F712E6, &hCD9DF681, &hA05A0EB3, &hBD1A8E76
Data &h1A809056, &hD4E80F23, &h105DA25C, &hA763D3D6, &h1549C175, &hE27B1EA7
Data &hD7CCBCB2, &hFD130F8E, &h2DB8A222, &hA3B1C2A7, &hBE2163BF, &h3F3859F8
Data &h1A6A99A0, &h6E9B061D, &h8AE3ADB4, &hAED5D571, &h5EFB2779, &h1EB81666
Data &h581BE78D, &h882D9D0D, &hD85934DF, &hA26FAA7C, &hA320DADE, &hE9E40841
Data &h59D20232, &h44D5575F, &hAF0BACE6, &h57886F3F, &hEEA02CFE, &h6160DEA6
Data &h958F9109, &hA87CE703, &h84F7ADB1, &hC3845853, &hBAD2C68E, &hDF65774E
Data &h2731287A, &h0D234581, &h4A14ABD4, &h64250AC1, &hD9ADAEB7, &h04A11B37
Data &h9243AFB1, &hDF937247, &hF70748F1, &h483F1E71, &hCB895863, &h1702FD45
Data &hF0453030, &h09EBC871, &hF8F82FF6, &hDFA349AB, &hA7A4ED13, &h9D61A8CB
Data &h5AD9A8B9, &hE475A2E5, &h4C3A9045, &hE5CE7088, &h81129302, &h42E06906
Data &h441C7664, &hBB275A77, &h2BAF6A7B, &h192FFC75, &hEF56233F, &hC05E10A7
Data &hE7FB7EDD, &h110DC791, &h055734FC, &h1D120C04, &hFB098857, &h5DBF0392
Data &h23CD8F1E, &hC006ACEA, &h4487BFCB, &h9109587C, &h15BC5374, &hDE9A714D
Data &h3AA04739, &hBAF1B034, &h9350525F, &h870F06EC, &h108C5DBE, &h9C099240
Data &h19D834C6, &h9FE22598, &h13EE9F84, &hDC0D9971, &h87CAAFB2, &hCCC4A0EF
Data &hCFF8D73B, &hD0AC084C, &h995DF29D, &h0BECA710, &h41AF89A6, &h702A3F85
Data &hBF07C633, &h8246AAE0, &h33CF6293, &hA49BD988, &h75835030, &h70F3F25C
Data &hCEC0A83E, &h469F1022, &h24E92B87, &h4A633409, &h2A8AD8C8, &hF2E9D6DB
Data &h2D003380, &hAF2C548F, &h21CEA02B, &h27F99679, &hAE32C2A8, &hC3F8D0F8
Data &h0342CA3E, &h73CAFE8C, &hE26C0745, &h27B17DA9, &hC991CE91, &hCC89C96E
Data &hCA6B352C, &hBE290D4C, &h30E0FAAA, &hCB3BFE1F, &hF79B610A, &hA9286EB8
Data &hBDE12F14, &hB1B491AB, &hC0FEF094, &hAD32897A, &hF4A04D8D, &h09FFEA05
Data &hA4FA3A50, &h1FBD6EBF, &hD651DEE5, &hCDA435E7, &hAB3F27E8, &h0B2E348C
Data &h04CEDBED, &h50F6F8E2, &h7E179662, &h2EC8E369, &hDE288A7F, &h510A39D3
Data &h69CF1A2F, &h8A29BE1F, &hEC29C3DC, &h902647A3, &hFBFD0EDE, &h08D6415E
Data &h3753AB37, &h40A7C1B5, &hE9931E46, &hC3F46E53, &hD4E900D3, &h5D3C4F32
Data &hCEFECE30, &h024774F7, &h0C3CFB63, &hAAB3A358, &hC1D833CD, &h75FB5118
Data &hC6B858E7, &h534EC9C0, &hA4AB8929, &hD33B92AC, &h403A94AB, &hB7460AD2
Data &hA39F4245, &h13BF3B70, &h7AF13BF2, &h5B83C48C, &hA9DFB70F, &h6A199598
Data &h0A41CE30, &h55735ADB, &h5DED277F, &hB1E8BFBC, &h2AD2E1E9, &h22AF9E38
Data &hDF5321B1, &h2E463E45, &h3BE5CDB5, &hA9288A48, &h8E79E081, &h2E3FD018
Data &h463146AC, &hFA08C37A, &h93CB9A8F, &hE43C9E9A, &hD2F431AE, &h9048F135
Data &h0AA729FB, &h8CF1DACF, &h55EC0A12, &h9F6ABD40, &hC1FB3BF9, &h35D8EFD1
Data &h0BB34288, &hD9466D8D, &hD1B45FF4, &hE09986FA, &h9C34AC4E, &h990D5123
Data &hC46FFF1C, &h9C4D053D, &h123860E7, &hCC34C412, &h84DC15C7, &hC3AE97B2
Data &hA6F88E54, &h8853856F, &h0FA23485, &hED2C9DCB, &h31207A23, &h7C2395E9
Data &hD3B1E856, &hFF0B39E2, &h87800555, &h07F836AD, &hEDE0B225, &h864D5E74
Data &hF4E6EBDD, &h70ED0388, &h24EB822F, &hCCDC8589, &h3E45CD3D, &h157D6C71
Data &h0D3808AB, &hED4053CA, &h5778D967, &hD352F7C4, &h8D5157DA, &h36C02EB2
Data &h91809268, &h3D8C55BC, &h8068D090, &h637C5FE1, &h29938E27, &h1CEC3BD8
Data &h2604C84A, &h5B74B537, &hAD0FFABE, &h0FF84268, &hA0AB2224, &hCF5A6F63
Data &h020493D2, &h1F315F5C, &h6994281D, &hA66CFB52, &hE81F46F9, &hC2272BB1
Data &h8D281884, &hF2825128, &h9B12FFCA, &h3AC670E0, &h2B390358, &h8D89D476
Data &h59AB5B94, &hB1EFC28A, &h5D9EA561, &h1BF9DA0F, &h40B2EC87, &h11577FBA
Data &hD603BC80, &hB8A75E6D, &h8B9EF1D9, &h98FD8D88, &h375815AC, &h81074A72
Data &h5C6EA7EE, &hAAF84259, &h372F8857, &hB66E84E9, &h7A167044, &hCAA53665
Data &hE3C94110, &hB3073D19, &hBE508C56, &h2157A3E5, &h3596E8F9, &h70C9BFB9
Data &h67EBA51B, &hAA389A5B, &hAE9EFB41, &h51F9E2E9, &hE3A60495, &h7683150B
Data &h55C72725, &h26FE00E7, &h439903F5, &h7435498E, &h06346360, &h448508F2
Data &h837DC9B7, &hAD778C41, &h42288A71, &h4E87550B, &hBCD672F1, &hB9AD03CD
Data &h33621B38, &hDCD2F4D3, &h99A17713, &h1714456B, &hA7065499, &hDC9DC2A7
Data &h77467CFA, &hB093EED4, &hF301815C, &hCAB249DD, &h831C30E0, &h7CC922E4
Data &h4A401715, &h2A6D18FA, &hD1D8866B, &h19B4C5A4, &hF5C5FD16, &h53557E40
Data &h6EA2D7DF, &hE03C5F7E, &h5B491E52, &h8B8B0473, &hE7709C84, &h3C55E41F
Data &hC2802D91, &hFE2216D9, &h5FDF0492, &hFF59797B, &h7A858D5C, &h0C5F6EF5
Data &h082C7902, &h408D0DAB, &hFC0D7E32, &h63AAC9D0, &h35A050ED, &h8B42C2F8
Data &h68F12D65, &hBCA6D8BC, &h90F3D681, &h7670F57A, &hF134FC85, &h57328D6B
Data &hC6CC474F, &h84E16F61, &h0A9328B4, &h8E63B01A, &h20A8D974, &h7F8263D0
Data &h9F426C33, &h4B1D111D, &h0BD8FECD, &h632C468F, &h227E97BE, &h036E4B14
Data &h5E84A85C, &hC1D2EE81, &h9701BC16, &hCE2C521A, &h78714EAB, &h57F581F2
Data &h0EAE6AAE, &h480EA1D2, &h4BD80188, &h0664A28B, &hE2ACCE5A, &h1E247794
Data &h8FD0A4A5, &h02450BE6, &hC045DF63, &h1C41B9DE, &hD5197787, &h7CA01B2F
Data &h306F55C1, &h84F5B522, &h7C55C72E, &hCBA50229, &h6226B9B2, &h289CA335
Data &h1D2C071F, &hF8F506F2, &h85424563, &h156CF31C, &hCA230963, &hFBE603F0
Data &h5B766D47, &hFBF0171A, &h167D0BA2, &h5990B229, &hC98A5CE8, &hFF79B4F1
Data &h07F4CA10, &h2CB5B12A, &h7585EA63, &hCC10DF36, &h4281F66F, &h6DA7CA5B
Data &h1A8F1A52, &h529632DE, &hB9285D28, &h6D82A769, &hDB287EA5, &h244504C7
Data &hD7293615, &h58975819, &h98865704, &hAA33A9B0, &h8F9848B2, &h6E5BE448
Data &h9B142A41, &hC9ADDA9D, &hFD0387F2, &hD53AE6F6, &h92C10DC8, &h7ACED1D5
Data &hD81B30CF, &hCE0221E4, &h9CFB3168, &hC3D3DE35, &hFCC69462, &h73584797
Data &hADC9182B, &h9185868F, &hB991F23C, &h8696FCEE, &hEC81B908, &hC4243185
Data &hBD5DCD44, &h3BD1AE90, &h9785DEE1, &h608B4C91, &hDDDE6CB8, &hA1AB4C3C
Data &hCD6EF209, &hBA0C5374, &hE632CAEF, &h4B0E960C, &h3BC72C3B, &h84685E77
Data &hB4D27AA7, &h53026FE0, &h76B78ACA, &hF33AE736, &h725E90F9, &hC736F140
Data &hE67F90A6, &h794D5F4E, &h7A9F5C26, &hBDBD7044, &hB6626BDC, &hC037DC42
Data &h74E72DA2, &hD9891BA8, &h2055EE6D, &hCAA08AEB, &h0512966D, &hEFFC8C64
Data &hBEEC1DBB, &h8D89F3B4, &hE3E5EDE4, &hCD869A43, &h5A734E89, &h9CFDEE31
Data &hBE6B390D, &h84FDE1FF, &hF2C1C50A, &h4268911A, &hE3A4899C, &hDE7B0850
Data &h5E0AF56B, &hF91AAC24, &h60508647, &hFBC0115D, &h1D943D87, &h51F4900A
Data &h6024463B, &hF189C663, &hBE8B6E78, &hA04A9EE2, &h0AE4E17B, &hCADE0EB7
Data &h733EEB6A, &h8118C302, &hA735367D, &h40FF0BAA, &h37F9D578, &hBDAE8C3A
Data &h74700804, &h55DCAA21, &h15E48D91, &h90FEE856, &hD6C2310B, &h28F28D15
Data &h4705D4D6, &h025F5286, &h1FFC4D11, &hF5651E56, &h3EDCB829, &hC3DC4582
Data &h61A555C6, &h8E2ACDDA, &hA89B608A, &h19E68088, &h5D3648D4, &h649D8AC7
Data &h0BB82818, &hEE447818, &h64A66E2D, &h42F2FB24, &hE51AD594, &h970DBD5C
Data &hDF775F1A, &hEB641D67, &h43AB0CC5, &hC4F88467, &h8AEF36EA, &hC0456B7C
Data &hBDCF9B52, &h082709D6, &h7A7AA233, &hF395FBCE, &h851B7931, &h605E5849
Data &hE31E8A8F, &h9D755CDB, &hBF7592E0, &h621885C2, &h7BE827F7, &h868B6386
Data &hC9219877, &h1196197F, &hDF8E40AB, &hE359C3F8, &h33E6991C, &h458B41B7
Data &h549BB3FB, &h3DF7DB0E, &h85A13DBE, &h0CD75862, &hC3808223, &h57CA141E
Data &h4B2FC137, &h09BAE650, &h0123AAE0, &h1295AE40, &h3EA647CA, &hABF7D0DC
Data &h1C77DE37, &h9E0DD87B, &h0C205EF6, &h87931BE6, &h986082F0, &h2F67592B
Data &hFE1BBAF0, &hD4C609E4, &h5B23277A, &h9733D854, &h690407C6, &h4181F076
Data &hB5034763, &h98C89AE0, &h7229C589, &h2E11601F, &h67EEAC67, &hD283EE93
Data &h604A0900, &h1B18C600, &h2E61741F, &hF6A56A04, &h8FE5C88B, &h3D6A9248
Data &h2513C9E5, &h893BB8D3, &h725AFDD1, &hB82FA00C, &hAD0731B0, &h617A2BB6
Data &hD7A25EFB, &h548E247A, &hB4394AC2, &hA473ED6C, &hCE446943, &hB1D1AE70
Data &h5E636FB0, &h229A707E, &h3BD639FB, &hFC8706A0, &hE381DAB7, &h1A2CCD4B
Data &hED9437A5, &h943A0324, &hCFF0E590, &hC5503C6E, &hF2F3AC69, &h83E5535A
Data &hF5525576, &h38E342D5, &h33F9DCB5, &h183C87B4, &h016B7EB5, &h9A0FB560
Data &h1F5A1589, &hEEB20A81, &h7AD0E2AD, &hADC0E2C0, &h630AC396, &h181C5722
Data &h5301ED0E, &hFDA28CD9, &h6F026739, &hA3A289E6, &h4A4141A9, &h396F9A55
Data &hE104F005, &h6A894F13, &h5E93068C, &hCE73CB6E, &h459ABEBD, &h0CC0128C
Data &hCA36223B, &hD26DFFCC, &hC6AAF10B, &h30EF5FCC, &h1A49FB86, &h487791AE
Data &hB6FA52EE, &hF55B3E47, &h9C902001, &h47959563, &hB70E8120, &h8E629062
Data &hFC812144, &h7C9681F7, &h4A687A9C, &hAEDEC6C5, &hC5C63819, &h7611FAFC
Data &h15F315E0, &hE64EA7AA, &hAFF1FE4D, &h1F07E4ED, &h48A6869F, &hBC879626
Data &hAB1ACD4F, &h5538569C, &hBA4667D6, &h0CD76E03, &h9B2D10FB, &h460A96BC
Data &hB6A7CB72, &h3FECE4C3, &h9FF3D0AC, &h2297A5CC, &hCA8DCB05, &hD045878D
Data &hB736222B, &h9C55F740, &hC21EAC71, &h7C62CBA5, &h3885E2A4, &h0E5FAA67
Data &h13E3B21A, &hCAD6F5ED, &h50DDCB01, &hB1C54613, &h31718D0E, &h54EE3B2F
Data &h5EB97954, &hB3FED7A2, &h21936971, &hBF0F53E5, &h9688B905, &hF4FF5B41
Data &h69510BD2, &h30DCC493, &h82246612, &h7AC0540D, &h6BB54190, &h7684CCB3
Data &h9F462C9A, &h7C8888D4, &h2DFEDE73, &h5F9E7192, &h6465592A, &h1550918C
Data &h6E122C5E, &hCB9FB6E2, &h6F9A0309, &h2925FE1B, &hA639020E, &h5E67216B
Data &h401F9CEB, &hEB2CAB73, &h7DF2A490, &hFD32DE26, &h2A57D5FC, &h17579531
Data &h74EDC259, &h8651A9A4, &h158D873B, &h8256E2D2, &h307A50B7, &hC4391875
Data &hCC53B7BA, &hE432C1DD, &h5A2FF338, &hBBAF7AC6, &h4B79CC75, &h7CAE545B
Data &hC82E18F0, &h50340E02, &hB32C7381, &hC3D43B25, &h1FEDD9C5, &h6E8DFC50
Data &hE9F6C787, &h4B317B74, &h9A30C1B7, &h47A077A8, &h7085289B, &hDDA0F3DA
Data &h7CE80C41, &h11215120, &h7246ABC0, &hB8C57350, &hC5F9C268, &h5E76853F
Data &h7266B20D, &hDCED5793, &h5D68F2BC, &h04C592F6, &h5BCF87BB, &hDFCBCDDD
Data &h7861C3B8, &hD9A053AE, &h59910314, &h7DB29D60, &h651A598B, &hBF6B1CCF
Data &h6413B94B, &hC6A56C85, &h65165BBF, &h152D2A83, &h69CCCA8D, &h36D34934
Data &hC6CF04A8, &h6CE7BD5B, &h518F5C5F, &h42A1D345, &h979FDBC4, &h2713B7B6
Data &hD7EF066A, &hF49E8AEC, &hF6B83BF2, &hE1BFC465, &h591B96D9, &hB119F0F1
Data &h2C9625FA, &hCCDE083A, &hBC26A8A5, &h767347EB, &hBAD34FDD, &hAA9EF9FF
Data &hF9821058, &h7ABEEEC5, &hEFBAB3E6, &h6A0187BB, &hE1426881, &h9A4166B8
Data &hD41F9857, &h45A76E95, &h39E301E1, &h82DA9024, &h79132F94, &hABFBD543
Data &h0DDE311D, &hA1F57B2A, &h94C44A10, &h4AB5B09C, &hE380435F, &h468196A7
Data &hE8BDCF52, &hA7CA1848, &h5FB6B786, &hD4F1F942, &hBD9B4815, &h13ED7330
Data &hDF6947B3, &h584285EA, &hFFE8AA7A, &h049A1E09, &h2F9ECC91, &hA937A273
Data &h4381087E, &hECB019E6, &h24AC460C, &h7ED23893, &h1E5718EA, &hF160B78C
Data &h12BB62DD, &hC4B20E4E, &h586B94E4, &h6360EE04, &hE97431FA, &h6503A21C
Data &h453CF5BB, &h008F8EE2, &h076E1007, &h9B845359, &hB659BF8D, &hFFF86B9A
Data &h6E72B347, &h2C95DB15, &h0C4D9208, &h4E98428F, &h5DADB0DE, &hACD44BCD
Data &h5413BF87, &h61C89F9D, &hDB5D2378, &hD2383282, &hB06A5221, &h27D1B3C5
Data &hA409B0C5, &h311BC861, &h31A3D628, &hDF5586EF, &h4AF851B5, &h3A9844D7
Data &h1B1F596A, &h96373D2C, &h5BECD4B0, &h4E287C93, &hB75E8381, &hC8C9236F
Data &hB541023C, &h3E0CEC2D, &h667379B0, &h484A4731, &h50BD2DC4, &hCF305E42
Data &h46B1BA9D, &h5C8353A6, &h4E5CD239, &h5D1B53F3, &hDA00AD1D, &hD384B7AE
Data &h5DBD9337, &h9A056768, &h020771BF, &h412E37E3, &h0FF681CA, &h2EB0EDAB
Data &h6D8AE7C8, &h0F97E92D, &h46A4650A, &h4D426E1A, &hE0D90DFC, &h896A0E8F
Data &h3FBE3154, &hDA687AAD, &h9EC9399E, &hF7B0DF96, &h79DC8223, &h0BA06DE0
Data &h12C3A3C6, &hAE48B410, &h30C4FCF3, &h2930833C, &hA5C0DAC8, &hA5B2E10B
Data &h8CFAE6E6, &h59B38A58, &h9882CFB9, &hF9FC0E1D, &h4152A052, &h705E63CF
Data &h82565CB3, &h2C52EA89, &h725EA0D0, &h99F0D089, &hC95280DA, &h8D359640
Data &h9B5B4860, &hB41DC5F5, &h186D7884, &h5A1469BB, &h2AD9999C, &hB49D8353
Data &hA78D2C22, &h5128099E, &h42F3D967, &h21BBEA78, &h3CE3ACD9, &h565A984C
Data &hB887E861, &h27974135, &h81A85359, &h6865A436, &h98BA90D6, &h6E743E7B
Data &h1BF36488, &h8B16F033, &hBB8D31A2, &hF4AD7405, &hBDE988F7, &h070B6A20
Data &h78C91347, &hF9579F86, &h2D07DB2F, &h1048987F, &h9F3110FE, &h8B789C12
Data &h92A166DF, &hAC3CD3D3, &h1B907BC8, &hEFC96765, &h551D3973, &h3F095A06
Data &hD9095D21, &h52826892, &h51A7BCDA, &hC17E546C, &hBE589B51, &h02FD24F4
Data &hFDCE71EB, &h009DC6B9, &h45A8178B, &hCF47F3AF, &hCAA2271F, &hB1F5A73B
Data &h1888BAEE, &h0447BD10, &h19D0D293, &h6D71F762, &h2C8D1881, &hEA1FD0FD
Data &h433F0367, &hD275DD63, &h45139797, &hB4295E0E, &h854FD940, &h3F7E046B
Data &h43FF11C2, &h87CB20E3, &h63F73B6F, &h9F75B2E4, &h26EF975C, &hCDEBDD2D
Data &hB760514D, &hBEC514F0, &h56579F9F, &hE3E95EF1, &h7F510418, &h576FC36D
Data &h0A0D6741, &h737C50BD, &h491FC7F5, &h96CC2006, &h4034E62F, &hB9D955D4
Data &h882E8A0D, &h829931CB, &hF4C76F9F, &hD1580A6F, &hCA33D887, &hCD95C465
Data &hE38246C0, &h7707671A, &hA8C0DBE1, &h510E0BE0, &h90824257, &hCC9CDFBA
Data &hAE9C6B3A, &hADE6E48E, &hE6107F60, &h3658271B, &h7D188914, &hEA7D543E
Data &hB3781E10, &hF998A4FD, &h8C0F9818, &h8C9C5BC6, &h352D88BA, &h4202E574
Data &h1CE62373, &h21942244, &h49C624C9, &hDFFB2CD3, &hFA076D36, &h9A33FB64
Data &h060679EC, &hC7C66AF0, &hBAD082C0, &h74EAE9EC, &h9A3D05C1, &h6351A20F
Data &h93A878C1, &h3CB6A5DB, &hEADA2AF2, &h5F17BD4E, &hBB201EBC, &h8B3AE3BD
Data &h6A44E7B5, &h4569E659, &hFC6C675B, &h0B4A471F, &hFCC0CDCB, &h7FAAA58C
Data &hC1536993, &h7E5E5C68, &hAE65042D, &h8CC4732D, &h2938F3E0, &h67B1FAC9
Data &hDEA69FFB, &h9F9E31E6, &hDE57163E, &h6F4391B2, &h51AF42E8, &hD393B7A8
Data &hAB7AA189, &hE34E69B5, &h300DF671, &h71AA4567, &hDDCD3260, &hE775AD0F
Data &hF685C127, &hDFE011AA, &hD8F7B8A2, &hA4869696, &h459666CB, &hCD1F596E
Data &h5F4CE954, &hDE4D900B, &h04B1B066, &hCB370249, &h6D0817C5, &h843C3C5F
Data &h5EE8641E, &h9417F9C9, &h081C5B17, &h996B89BF, &hAA672071, &h39ABFC29
Data &h09B37B6C, &h5ABBA857, &h1BD014BC, &h7C2021EB, &hB14A9C8E, &h684FC81E
Data &h3A27C1F1, &hED0AA490, &h970FB694, &h57A1F217, &hE098D10C, &h20FD7AD3
Data &h64BF140D, &h0A663944, &h2D282F26, &h8D115457, &h384E1483, &h48C3EF18
Data &h4163A431, &hFEF356D8, &h266A8DCE, &h2D767D0E, &h06B5D909, &hC775578E
Data &hDB1A3C80, &h01E87AAF, &h2F7F8572, &hFC792B1C, &h346EDBBC, &h139AFD54
Data &h1F48737F, &h4B0A5F7F, &h8BC21739, &h0498EECA, &hB3940F92, &h125C1CFE
Data &hAE5721B2, &hDEF38AEC, &hCFD63AD7, &h634606B4, &hE8AA9074, &h74FFE859
Data &h735E21B2, &h26B7AED1, &hD2F14DB4, &h7E9A32BA, &h2757D3EC, &h2E39377E
Data &h9DA5F5F0, &h067B6999, &hC0D6D5D6, &h75E30BBF, &h88044740, &h76BF5048
Data &h8D308075, &h4431A233, &h0386EAD3, &h8DA94D7C, &h39390F2E, &h081EF2BA
Data &h91C31F88, &hF94FAAA5, &hF0BCFCCB, &h2D5A7C10, &hD3CB48DF, &h8430D9BE
Data &h850621CF, &hE0724CD7, &h7FFF1711, &h51A1AEF3, &h097396EB, &hEF086754
Data &h8EF9A4AF, &hF675A87E, &h0AD8C9BC, &h2BBDD442, &hA8E09973, &hABE34E11
Data &hE8C7325B, &h45E473B6, &h2AFBB9AE, &h19C37393, &hBB4A552E, &h878CAEB4
Data &h9A2349CB, &h3D20C10D, &h3BF62DC7, &h74200299, &h0CC12587, &h416F1CD5
Data &h896D11DD, &h7912A003, &h8774F49E, &hB597CBE9, &h51E9FE58, &h6B972CF9
Data &h6AD6EAC1, &h097CA991, &hB3CFA933, &h6A34BD2F, &hC59EC094, &h9C6A6893
Data &h7AB5D007, &h64303D69, &h35CB1F10, &h56303A23, &h8C30F94A, &hBE79C38F
Data &hFDC15284, &hBEC6B4F3, &h109672A2, &h4372532D, &h6AD31EFE, &hAAE4ED63
Data &hB89EB07D, &hADB8B93F, &h68A0ECF1, &h41E04F38, &h4732C73C, &h215A50E3
Data &hF295B2D3, &hBEF53019, &hD6838D08, &hB7FB85E1, &h2D7372CF, &h063C866C
Data &hBD07A703, &h7E45B1D7, &h368D854E, &hBC0D3E32, &hA4B2A6D2, &h458F2F6A
Data &hFA1D4F4B, &h11D0FB9E, &hE3712AE6, &hC26D1B14, &hC6AE566D, &h0D5E3BD7
Data &h57E9D1F3, &h254B2675, &h5CB57A70, &h7C4E6A0C, &h0D731858, &hF88120D4
Data &h3C272DAB, &hEEE381A6, &h933EE4B7, &hC53FE9CC, &h692F9088, &hB6F1E906
Data &h95E3CEF8, &hF3DBA315, &h2027A6EB, &h2FEC2FEF, &h212E2584, &hB4EC766D
Data &h6C1CD7AE, &h086709A9, &hC17E1553, &h2335D286, &hBC68401D, &h006546BB
Data &h1680106D, &hCFDC92BC, &hA4010CAE, &h2E8906C6, &hDB68700B, &h9E2FEDB3
Data &hFCB9BF5E, &h07B2B913, &h2036A834, &hE0E25E85, &h9BB0440A, &h5A392A33
Data &h46171020, &h4CE2C5B3, &h2AE0CD80, &h2D25C1E3, &hFE9E545E, &h7197BC64
Data &hD78C08E7, &hE1338794, &hA0B6E4E7, &h903EFB34, &h30508DFD, &h9F21B8DA
Data &hC7B16A39, &hAB670EEB, &h4B5486CF, &h8804982A, &h5AE4B79E, &h09B24284
Data &h6BB18477, &hD0B6BD41, &h37E46B5C, &h5A4D4384, &hC251362D, &h3E8EA4B7
Data &h3BFABB19, &hFAD7F9C4, &hD98AF7A4, &hF86222E0, &hF7909499, &h1CCFA4DD
Data &h61CE20EA, &h9C9E7F00, &hA42A5FCB, &h51F286EE, &h942D7A60, &hD2AB1B85
Data &hB08493CD, &h0B698BC1, &hDF4BE8C0, &hA91CC36F, &hB1D6A7A0, &hF64008E2
Data &h356AF04E, &hC46A922E, &hE4024327, &hC51F1C97, &h3DBACE41, &h620F86FB
Data &h8939589E, &hE6B80EAA, &h039AE7B5, &h7ED51F86, &h4F8FF6B9, &h15B9C002
Data &h55E24015, &h1118A5CF, &h5F8DFF1B, &h6D105136, &h832D8E4B, &h70D86ED7
Data &h81FCE602, &hBDD7A072, &h9087A158, &h52B2D96C, &hA39A154F, &hFE288A2B
Data &hB235CF10, &hC68F245C, &hF6E835BF, &h5CA42C8F, &h07268DF1, &h5DB61D83
Data &h20F4160F, &h3EAC37FC, &h6B9F7051, &h3811946C, &hE58B2E9A, &hF22CCD6E
Data &h4D576307, &h84C238BF, &h5696BE41, &h9ACE908B, &hCE12E3CF, &h67C6F17F
Data &h2BAF9EB9, &h891273A5, &h3BCE5FED, &h24CB2AB4, &h5357A72F, &h3832D7E8
Data &hA309D1D3, &h5CEC9E25, &h6CB89054, &hB1F3020D, &h3B4C2EE8, &hB7207ADD
Data &hDF954300, &h1B95B2AB, &h7BE4C101, &hE58C0CF9, &hBE6D3570, &h800DCBC6
Data &hB0B4C56C, &h6E52ED68, &h077FFCC0, &hCD74D502, &h1EDA3266, &h2A252CE8
Data &hB6977431, &h1E3CD6C7, &hCE3515E9, &h80E16054, &hF659FC0A, &h1E2031B4
Data &h20259E77, &hC278AF25, &h71A94667, &h4C06F1A1, &h7CF6F01E, &hA74C1087
Data &h2476C39F, &hF8048B21, &h6DDD2C08, &hD85C47BB, &hF2B0BFA7, &hDF0093BC
Data &h13AE38DC, &h36D6C1B6, &h52330779, &h3F28EB69, &h13CD7103, &h819B1F9D
Data &h59F696DE, &h1AF48324, &h4F06E323, &h5EC190C4, &hC20B443B, &h7B62E802
Data &h18043222, &hE39E2F8A, &h57A1CF67, &h71ECFF7F, &h6F300327, &h263BDC5E
Data &h14D5CE54, &h3839E709, &h1F3C99CA, &h0C5CDAF0, &hD07B0339, &hE5DE19A6
Data &h81510991, &hD38612B0, &hE313F531, &h5CC47A41, &hCD59AAD1, &hDBA00C3B
Data &h7AC2042E, &h89C08145, &h35F90BDA, &h8B9D42A6, &h20D858C2, &h11C8F9E8
Data &hD3E155F3, &hC2A69306, &hCB483D71, &h2104CBF4, &hED9F0F7F, &h532053DD
Data &h4EBB78DC, &h0E75E948, &h2462AAED, &h5A42DE2F, &h718D036F, &h57741C17
Data &h77A305A3, &hBFAE0978, &hA2B0C2B0, &h24501593, &h488412C1, &hD0457E67
Data &hCAFB4B40, &h8FFB1C1B, &hF6786ADD, &h315E1C4E, &hBB246D25, &h1C075706
Data &h823E409C, &h6D80CF62, &h7C07B95F, &hD4A508BE, &h0E485EEA, &hC7C181F3
Data &h2EE33FD9, &hB7769F51, &h302F1241, &hAF5584FE, &h31B2FFA2, &h5659868F
Data &h0D101345, &h82B972BF, &h1E76D3EE, &h727A35A3, &h6945DDD6, &h14E2B0BF
Data &h8AFC0DF1, &h11F240C9, &hC558451D, &h36CE9339, &hB29BE77C, &h0C629634
Data &hA923E718, &h2C3046F6, &h7E1C6119, &hC89B7FBC, &h5C1ED869, &hBF577EAF
Data &h0FFD9C2B, &h8D81B7B1, &h397AFB66, &hDC2A9323, &h7C84167A, &hAA6A3BE9
Data &hA54FEB1F, &hE2706CBE, &hAE847BF3, &h0970A6AC, &h75CC228E, &h5538D91B
Data &h2B0701D3, &h3B47B58A, &h8831A7B2, &hBC75043B, &h480B843B, &hB25C832E
Data &h9AFB05CF, &h2B3D3292, &hD82D819D, &h8DF42AF2, &h2EB4C326, &h10175A29
Data &h83D85223, &h79258759, &h36D3AA0D, &h6AB8AB62, &hE15C42BE, &hD5F70942
Data &hD9E804CC, &h1B5D47EF, &h12B23863, &h339D6265, &hB0E989CE, &hE6AEF1A7
Data &h5BA4E71C, &h16533B07, &h40DC8BF2, &hA5EA8724, &h669B599D, &hF9398A58
Data &h648EA71E, &h8FF72DC6, &h748BDD8B, &h514BB11A, &h8AB428DD, &h39100A20
Data &hDB636620, &hB1756C82, &hC4926E02, &h4A04A933, &h215BFBAF, &hA8ECEDDF
Data &h1DF298F5, &hFF0B65E7, &hC6C28EAA, &hB8B6E038, &h03C0EE88, &h4E0509D2
Data &h9B69A620, &hEF504050, &h4BE3981E, &hC313DB00, &h123ED817, &h6C49B7A4
Data &hF4469D6A, &h1FC9E163, &h63E9D33D, &hA9A0EA6F, &h640B1F83, &h23D3EB6E
Data &h1D380818, &h93120A4A, &h00E76CD8, &h0E513946, &h24DB6429, &hCD2CCF40
Data &h28A02365, &h6D5C83BA, &h0D074070, &hECB9E3F4, &h43725081, &h6DFFA703
Data &h2A3B60C7, &h0A56E2D8, &h50718E1B, &hAB5DDA46, &hC4504DA7, &h3C0FBB76
Data &hD1A6123C, &h9049DDE7, &h42503EBE, &hCD812B99, &hAA9F4460, &h46C0F2BB
Data &h88151D06, &h5FA27549, &h5ACA7794, &hB5CF07F8, &h5ADE44D4, &h7D1CC0EC
Data &h770C1723, &h379B1180, &h2E74581C, &hD5F87A1D, &hE5156CEC, &h1821F639
Data &hC81CAA11, &h1CBB0A89, &hE2905A9B, &hB7320309, &h4F413520, &h86008824
Data &h3FFEE60E, &h3A6B02FA, &hB6FB51EE, &h9FAAF98E, &hA1847849, &h10308B7F
Data &h630C1A4F, &h63DD1383, &hDE835C83, &h4B8A88BD, &h339D41DE, &h8F99983F
Data &hDF59C539, &h692400E7, &hF5D58725, &hF9549806, &h8C1449B5, &hD757352F
Data &hEEED8963, &hC42EF59C, &h7C4C9E3F, &h234D4C8F, &hB77BBCC5, &h86C061E5
Data &hA3B059FD, &hE31450A1, &hC55829E5, &h31EC12EF, &hF66FCF7F, &h4B2A6301
Data &h4854E66F, &h2187F45A, &hE5983928, &h301C7277, &h52DD3B84, &h758B38DA
Data &h68041387, &hB37F3AFE, &hA90A1810, &h278D2A44, &h4649FFC5, &hCC220E14
Data &hB73E2619, &h20507B00, &hE94E5E1F, &h1478FF5D, &h98BF36C6, &hD977AD7E
Data &hE100B357, &hF4910651, &h2DFDBF9D, &hC01AE946, &h8333A2DD, &hA8AE4B24
Data &hB0BBC43C, &h21F6D9CE, &h1DC5647C, &h17426F0F, &h200D63E2, &h22F74AB5
Data &h5BB493EB, &h8244DBF5, &hBE86E92E, &h11153B40, &h24E19114, &hC007DF25
Data &h82843918, &hD66E231A, &h1E9BC701, &h8BB4CFDF, &hD3970EE9, &hBB6B3938
Data &h0D7E0352, &h96D97A9D, &h925D1EA2, &hAFDA7044, &h3550577B, &h2177D21C
Data &h84340C21, &hD7F52836, &hEB71EA83, &hDF414CC9, &h8BDCE206, &hCA669426
Data &h01A9AE1D, &h46EF26E5, &hA8D24E4F, &h08328638, &hCD7358D8, &hD1A610C9
Data &hED9FEC16, &hD0C2E094, &hBFBD1570, &hD2377D4F, &hBBCE784C, &hFC8F04FB
Data &h260B8BE4, &hA45F1A32, &h629A672C, &h0910A970, &h6FE54C92, &h0F544207
Data &h692B59AE, &h89B2E68F, &h5E5C561B, &h6B6E11A4, &h2E5280F6, &hDF30897F
Data &h7D4004D7, &hAB93455C, &hF4DAE815, &h0D79719A, &h19863888, &h5F0987E8
Data &hE8858A5C, &hB9D7A8ED, &h3F6E221F, &hBE286D16, &h21ADBDD4, &hB1F0DC14
Data &hD4D0DB30, &hADB55F46, &h51A32DAA, &hD9B81467, &h26019A52, &hE9907925
Data &hF3AA2385, &h7C03BB82, &hCCAD1697, &hE4B0A0A0, &h9BE0FD24, &h938DB261
Data &h950B6048, &hC23F3641, &h29CDBDE6, &h45800DEE, &h4246356A, &hF209363B
Data &h2489DF6C, &hC31B80F0, &h8F538885, &h9D870D6B, &hAB041423, &h2DDCC519
Data &h186CD890, &h756B3A95, &h44DF9D86, &h5E04753D, &h353034F2, &h65C8FFFC
Data &h8F9E5262, &h3234955F, &h95C72840, &h2F9C2C84, &h6E7C5BB1, &h0C6894AC
Data &hB04C7130, &h11683CAA, &h9F2B0221, &hF1531B37, &hBCEAB730, &h6432ADC8
Data &h9EADBC70, &h4BBFB336, &h5E3A0795, &hFBBAF5AF, &h1057575A, &h56E2162E
Data &hCAD68828, &h498D2479, &h1D470C0B, &hF6E19584, &h3CA104EA, &h128D78CD
Data &h97B9924E, &h77A56ED9, &hAD17BD13, &h90EA81A1, &h85FBAAB7, &h2CF14283
Data &hDE0B0DE1, &h6B975E74, &h6C1F171E, &h62E5D701, &h97155DCF, &hC23023F3
Data &h199899FE, &h7E21AC75, &hB344DAC1, &hF387D205, &h7866B8CF, &hFF9DBBAF
Data &h645B2932, &h0571A985, &hFAB38FF8, &hCA7039F5, &hF01BE4C8, &hD7A25620
Data &hF11E41D8, &hA1EA563D, &h73129FC5, &h633DDAB9, &hEA7FE7C6, &h20EE92AB
Data &h51480A46, &h6284C357, &h1392C0CA, &hA1998100, &h91AEA426, &hF5DF67EC
Data &hEC96F84F, &hA64F18F2, &h5F2D7613, &h87C8E359, &hE636B2E1, &h44A789EB
Data &h7DFE2DA1, &h7C819B75, &h73039606, &hDCC46044, &hFB34B2B1, &hA19C0770
Data &hE3E7617C, &h97F8B216, &hF0910D9E, &h292AA1A0, &hAA8D9D21, &h4047B4F7
Data &h90C12417, &hE84D0304, &h8CEED53E, &hC778068B, &h13828C96, &h7F349F13
Data &h3C030D8F, &h0A1E26E9, &hA39FF268, &h5CA22C13, &hA186DC80, &h848FBD18
Data &hC91E91AB, &hC2761032, &h7CDBBE7D, &h99B85B6E, &hD1957244, &h8642ED3A
Data &hDA7ACBE7, &h690810A4, &h444FD014, &h7442832A, &hC1CE4F8D, &h9574B304
Data &h45BB16E7, &h1F562DB5, &h05208F22, &h22F02FCE, &h824586AE, &h90B4F1CD
Data &h98171FA8, &hB85CD9B6, &h09898496, &h27B7B3A9, &h09D7F8A8, &h12B790ED
Data &hC18762D8, &h448BAB6A, &h0BD10983, &h84706365, &hF3A762A8, &h1692D630
Data &h5C14DCF0, &h00CB4531, &h277AEF39, &hA1E37B9F, &h4B7245F5, &hC9450F16
Data &hCD91A08D, &h13040C01, &h218505AC, &hC1252EFB, &h9EF3F54B, &h52E7025C
Data &h7DB21EFA, &hE5FBCB02, &h64C2B02E, &h49A8BDC4, &h9320DEB7, &h24B2EEE3
Data &hEBA22577, &hA13C6788, &hC72E7637, &h4DCB8351, &h88A48A0D, &hBA9234D3
Data &h29937D39, &h2F4DF282, &h2CC57D75, &h7CD9DCEC, &hC72C4AB6, &h5DCAE30B
Data &h18FA40EF, &h6ACA9D70, &hB2369028, &h2C5C747A, &h0F9F2A83, &h159A0643
Data &h5480A78C, &h87A52DFD, &hF96C3B28, &hDA3F6106, &hF3921309, &hE5910025
Data &hF6616AB4, &h79A1328C, &h1BC3098F, &hD23CA893, &hC8DAA359, &h9FB94F76
Data &h5C000307, &hC3AF7F72, &hEDEDD2AD, &hC8297C6A, &hE970DB68, &hD25FBF43
Data &h7DD59268, &hFB344EBA, &h4F28E17E, &hEE3B718A, &h4A11FF21, &h2ABB6704
Data &hBA7013E9, &hE64B91C7, &h94668756, &h8FCBD8F3, &h9D0C0EA9, &h06CC229F
Data &h471B6DE5, &hF0174987, &h36F73E69, &hEB2A0718, &hBBCD2AFC, &h484723F2
Data &h58662B5D, &h82B5BF8C, &hC4E81079, &hDF793848, &hBFBC46EB, &h549A4234
Data &hDE587007, &hAC8EE051, &h473D105E, &h6253E7FC, &hE1764A74, &h8AC47FD7
Data &hAB634876, &hF95B7DF1, &hABBFCDB3, &h6372D99A, &h4DE14A4C, &hD857449F
Data &h4A91AA04, &hBD4B97BA, &h9513255F, &hBC3C19E5, &h5AC14C71, &h1D614FA2
Data &hF3E9B6B8, &h8A216CBF, &hFF9EA1EA, &h9367894D, &h3CB2DB1B, &h17313A3F
Data &h5DC3B8A8, &h85855AA5, &h351562B9, &h29DC491C, &h65B37154, &h6FA96927
Data &hE95298D2, &h08E848B1, &hA8AE0077, &h2D276663, &h1D3D6A5B, &hF1C11989
Data &hE218953C, &h342C83AA, &hA78C2103, &h885D5CFE, &h8FEBEA64, &hEA90146C
Data &hE9363CA5, &h3F4F534A, &h3FD7BEF2, &hE7F670F1, &h6207AC21, &h1667B400
Data &hAC9FC503, &h9A510C5F, &hABAE0149, &hADEEA96D, &h0A19CD5F, &h60391048
Data &hD149AA7E, &hA51EBB35, &h32C690DA, &hCCF230EC, &h9A00750B, &hC984796E
Data &h855E658E, &hCEACE624, &h8014817B, &hBD2B97C0, &h13CCB2C7, &h2346EE95
Data &h7733E12C, &h3A3AA830, &hEF7ECC46, &h0981236E, &h128A1492, &hEACAE23B
Data &h2CB5EB40, &hDC5776A8, &h4903DA1B, &hE1EABC8B, &hD21E7C3C, &h61B5EC82
Data &h11993C5B, &h2560CD64, &hF0F27004, &h3F4D7695, &h46979980, &h5501C35F
Data &h5562F289, &h4664E370, &hD8135B51, &hE7AFF672, &h444D483D, &hE6C7DC92
Data &h58765A24, &h95CC28BF, &h5C000ABC, &hE2381285, &h54E70465, &h9657FCFE
Data &h439D0179, &hF21124EA, &hBD39B18A, &h2469AAB8, &h7491829B, &h6A0E9649
Data &hC8A8BF23, &h828C4313, &h910BEC6B, &h16A2A604, &hDC946BE5, &h583E4F0F
Data &hF758EA5A, &h46B9C5BF, &h5E1B7476, &hB27DB950, &h69C61D4D, &h3DDFCD66
Data &h9EF9B3E2, &h19CB14B7, &hB29BCECE, &hFCAC9E87, &h77A8DB28, &h3970E578
Data &hA07E63F0, &h52E542D3, &hD738C2FB, &hFF0B5408, &h1A4832B3, &h743A405D
Data &h6AD4E26E, &h71C48CCA, &hBC2D54D4, &h53C804BD, &h64020289, &hA0AFC6E2
Data &hC842FC95, &h767FD591, &h86BDD163, &hEB0378D2, &hDC1815E0, &h74C4FEF9
Data &h6E16C2F8, &hFC9D986C, &h1754D661, &h7F7832B5, &h73F15CDD, &hC7DA8648
Data &h98366EF1, &h446C2ACF, &h1F05562D, &hFFF1B5D6, &h297A7D91, &hACFDB345
Data &h1E56CF34, &hA3197C70, &h48B9450F, &hD7D9F4CB, &hF6C0284B, &hF170DB90
Data &h6F8A9B5E, &hC8AA2266, &h904B07BC, &h1DD70A0D, &hAAD5E024, &h7EEA7133
Data &h6D787202, &h1000C278, &h4ED4E9FA, &h72A663CE, &h990EE12A, &hC1C035FE
Data &hD284BB20, &h956435B6, &h80650311, &hCDDD5130, &h89EAFD43, &hD8FF3002
Data &h04FBA729, &h3BAE4B21, &h87E19CE2, &hB0B1EC38, &hB1D17871, &hB13D1374
Data &h92FD0D5F, &h63EB0D93, &h02129BD7, &hD9F343A6, &h935EB149, &h4297B2F8
Data &hD8E26A51, &hCB596D10, &h16C13404, &h74CA49B8, &h890DFBE8, &h043A6794
Data &h1969BCA0, &h0DA383B3, &h9C69A276, &h4BAE4F91, &hA229547F, &h015FB04D
Data &hFA1E7EE5, &h590FB4BA, &hDCEAE909, &hA1F4E4B2, &h43E436C5, &h83CA7FFA
Data &h053351AF, &hF120EF57, &hBE6E7071, &h527B8C96, &h0DCA584B, &h451AA3E5
Data &h20BB5E76, &h71335DE9, &h12AE088B, &hF1C0F9CA, &hC3ABBAFA, &h989EEA0D
Data &hF9494D89, &h190CD8E5, &hFFEEE2E9, &hD7149FBB, &h5895C757, &h5E01C2EF
Data &h827E54CA, &h57291BEC, &h25C3526B, &h905FCDE2, &hC3E3229A, &h03D3BF98
Data &h6375F7C9, &h0683DD42, &h0F038B9E, &h1A310136, &h5A2EF515, &hAE0278A4
Data &hC8E70874, &h85E93DF6, &hA94D3943, &h71118FBD, &h40929A05, &hE83F4FBE
Data &h81DFA624, &h769D6E22, &h47A51878, &h4E9EDB6E, &h9840D587, &h40DB67A1
Data &h7A272365, &h67036024, &h8B056CC2, &h4CD4665D, &h4585D504, &hC544B19B
Data &h1CC8C006, &h6BD0068E, &h50D06564, &hCCFD68BC, &hD800D0ED, &hE42D429A
Data &h50CA60EF, &hB6FA8681, &hC2C0BAEA, &hC58831AF, &h26F51179, &hDE026DE7
Data &h652AA09F, &h4DEE029F, &h6FCA14BA, &h44C93D25, &hB92A0DA0, &h6CD600C6
Data &h5F9133E2, &hB53B1C8F, &hB4EECD8E, &h78DE5576, &h300037C7, &hEF7F1FD5
Data &h6142DC50, &h54A1F455, &h2E55CD59, &hD9B32A73, &hE04291BA, &hB6A6DB0D
Data &h529BA9BC, &hDB661276, &h4C047823, &h4914E37D, &h147CA8E3, &h1058387A
Data &hEBA56BB2, &hB0DA15B3, &h2FDC7422, &h5281C235, &hD70EFED9, &h584207A7
Data &hCDA38C3D, &h03F8013B, &h32DF3A3B, &h2BE87FB9, &h163AE7C3, &h7C91C083
Data &h4B11636B, &hF54CC8DA, &hC894DAA8, &h3CCCF6E8, &h2BDF26D1, &h30471EF7
Data &h26C55D51, &h87A5A13C, &hA1A94899, &h35357CF3, &hA0F7B4EB, &hC06F8DA0
Data &h0FB721D3, &hFFF6BE29, &h38ED1891, &h3A695E69, &h628EA410, &h8BC644E4
Data &h580C240C, &h89565880, &h2F3DF1A4, &hB2E064B8, &h45880D74, &h05B5B912
Data &hF368881F, &h9E550B99, &h42CBBC10, &h0C1DE34A, &h3F1A2157, &h7B2CC846
Data &hF6103BD2, &h2C1A3B28, &h65B42497, &h8F178F62, &h5DA5139E, &h985E9A01
Data &h21EFBEFA, &h734BD61C, &hA258856D, &h46582148, &hCB48E1D2, &hCCC730D2
Data &hF1A3E502, &h9BD3376B, &h83F8AA6C, &h3DC290FB, &hA7D010F1, &h5C498C49
Data &hE71CD849, &h4E289DED, &h0CAC11B1, &hBC048F9B, &hAD33B6D5, &h8F046332
Data &h0D74FDEE, &h3B09E517, &hEF86039B, &hED94DFC0, &h32189E1B, &h2083C889
Data &h27DC0BC5, &h8B6A2F31, &h199952A8, &hFC665F04, &hD63B4833, &hF7FC38F5
Data &h299E27F2, &h51D0BC77, &h1D2361FB, &h303EDDC2, &hB1F28DD7, &h42B57143
Data &h997B63DB, &h9E903898, &hA23015F3, &h1A9DD492, &h0CB28B72, &h2E989116
Data &h9275F752, &hBB8186E5, &hA887FF29, &hC5934664, &h86A8265C, &hAB9D8F26
Data &h7EF558B6, &h90011453, &h56F8E93C, &hBC791276, &h65AD7ECF, &hE03AE414
Data &h60F615E2, &hA440D53C, &h209DD83C, &h1F072EC7, &h69169585, &h1292F775
Data &h95983821, &h570D79A1, &h999EF8DF, &h27C13FAC, &hD97F6109, &h208EA98F
Data &h35442961, &hF1F4234C, &h63122446, &h114155CA, &h1A7E6C3A, &h13802C4B
Data &h538C7E56, &hB1985021, &hCDF268DB, &hAA864E0E, &h653AD05C, &hE2EF650C
Data &h9A07953E, &h191EA6A0, &hF10357B0, &hFB5FA9FC, &h882C4CDD, &h68CE70E8
Data &hE128EA66, &h1675AA84, &h6AAE4E74, &h754D5774, &h9B551C0D, &hB773587F
Data &hCF9FD626, &h34EC873E, &h977D2C15, &hC4DA12E0, &h906E6AC8, &h36E422F9
Data &h01A7C5F0, &h7F02C36B, &h4FEA492B, &hDA1198AB, &hCC8E5F19, &hE4EA0012
Data &h657E6858, &hC322909A, &hCCF89938, &h456AD4D2, &h4EA0E7DD, &h32384C80
Data &h4F77C17B, &h91D081E6, &hEE101CA8, &h6099E0FB, &hF09F8BCB, &h4146A9F2
Data &hF5B0CDD5, &hE44B7571, &h39AEA3E4, &h20E1801D, &h70C72884, &h53ACB5A2
Data &h137DC958, &hA5461E48, &h3E5018A6, &hC1B7D996, &h62B2CF90, &hA634A137
Data &h6F4DAC8D, &h763ADB0B, &h596660D1, &hD3065762, &hC1FA7733, &h4BB0F8FF
Data &h400694D1, &h301E0725, &hAD512EE5, &hD3C0E317, &h73A07A94, &h745AFD22
Data &h1310F162, &h66FA40A8, &h48E6F8C3, &h1C30128E, &h75EB29BA, &h07C20507
Data &hB7E49216, &h7C1B03BB, &hA39306BE, &h68CCB017, &h0B7E571E, &h41D3E212
Data &h48F48C7E, &hDC15F7E7, &h1C91E810, &h24A0E41D, &hFB5B8F39, &hC7CB6F53
Data &hD8440696, &h7D7262DF, &h13C77293, &hF7B19269, &h87DA970B, &h3CEB443D
Data &hB9FC62A5, &h8CEFAF6C, &hF92829E0, &h0F9883B0, &h5EA58D78, &h1ABB1685
Data &h093B2C57, &h3DAD8F27, &h2BDFE222, &hA51A02F4, &h51D3ED03, &h9C6FFA31
Data &h3662B8A2, &hB70B47CE, &h7CC34953, &h4FE38F86, &h53FEECF5, &h6C039AF0
Data &hE8DC829D, &h78EA6BF1, &hDD8B9403, &hC3C38DE5, &hA76EDB2B, &hB8B90B0E
Data &hCEAF575D, &h3CFE3F4E, &h8C01BFA5, &h50704332, &h2ACB848D, &h6D27F6AD
Data &h7BF5BA80, &h7D196600, &hE9C4A947, &hD0E68714, &h579E39E2, &hCA2F27E3
Data &h9754C5A9, &hD3D25F04, &hFAE9F432, &h2D828AA7, &hF538824D, &h8BB421ED
Data &hD6B2A750, &hF1463B12, &hA7605EC3, &hEEBF33F4, &h4CF73FCA, &hC7B7BEB5
Data &h71AA2384, &hA076B047, &h03EEB347, &h77C72968, &h9B5277B7, &h3464A6C7
Data &h20674540, &hE5BD6BFA, &h8A898170, &hC28AB2AA, &hF1EA3EB2, &hF52A1A34
Data &h9566C09E, &hBB95FF1B, &h6850C54D, &h9794C712, &hDAD9F3B0, &h73743D4E
Data &hA53AA186, &h69808809, &h6FAA8B78, &h631AA798, &h9E659846, &hB37F0066
Data &h96A64F48, &hFD7D00A3, &hE50F1649, &hA887A830, &hB70C672D, &h35E26845
Data &h556043FC, &h114C67E4, &hEEEC2E06, &hBE0D4F2B, &h632811CE, &h7FEA57E0
Data &h743C220B, &h733B0865, &h0704D447, &h689C53FD, &hC51B4C5A, &hA799DD15
Data &hC0D70B25, &hE6F7BE2F, &h1D45458E, &h75FDD1AC, &h05DEB07E, &h1E67574E
Data &h7278925B, &h598E90C3, &hEBDBA3ED, &h180283C2, &h78E511D4, &h011560B5
Data &h3A0856A9, &h378FA967, &hFEE0BFE0, &hE84DA5E5, &h82AAB515, &hA263D45F
Data &hA1D03DB3, &h88491FAC, &h946001DB, &hB9FB085A, &h0D11FA1E, &h531EE1C0
Data &hE606A39C, &h5EC2BF2D, &h4A1D959C, &hC9D682FC, &h3585D74E, &h74A6DBD1
Data &h22E987B6, &h2F5E7863, &hC0617F32, &h63E2CB6A, &h2E69E30E, &h91DEAF18
Data &hC6A44136, &h97B6FFB6, &h3276F86F, &hCAC17D92, &h270AFA5B, &hF7B6E59C
Data &h270A8071, &h54EFDD0E, &hD17D9BF5, &h7C58C1F6, &h9A718729, &h042801AA
Data &h91B0C37E, &h7A13A336, &hD7AB3046, &h4C24ADC4, &h0D6833DA, &hDB5BFA8E
Data &h6BC3FF3F, &h15CEC01C, &hEA124831, &h704EF441, &h3D31A6F3, &h5DB63331
Data &h882A1870, &h2EC64A97, &hD9EBADC5, &hFC906750, &h56D784A9, &h532553CD
Data &hD9E6AF89, &h1DC0EB16, &hED8E6759, &h819A53D7, &hE3D8B795, &h55EAC745
Data &h0CE3191B, &h44DA1D93, &h6E87ECDD, &h1C617FC4, &hF024F113, &hDD5BA817
Data &h5A3A8C81, &h12800826, &h51440722, &hED0473DD, &h77126C8B, &hA091F0DB
Data &hA00EB819, &hB0860C3B, &h23683C85, &h3BACAA24, &h50E653C8, &h1C17E355
Data &hB279AE56, &hA4A43E66, &h048D9987, &h5FCAA4ED, &h2354F713, &h90B0FC0C
Data &hA03CC64F, &h34305D6C, &hC9E23903, &h987FA02F, &h178688E7, &h999CB419
Data &hD45B8AD3, &h07C0E614, &h0F36B124, &hEA86B2B9, &h8EBE6090, &h0267D3F2
Data &h1FEC9954, &h39593995, &hB20523E6, &h73868C0A, &hAE9A939C, &h2A191F2C
Data &h6342F980, &h23D06EE0, &h14F636E8, &h4B640A5A, &h1CE019CB, &h53774194
Data &hD04AB644, &hFB24F404, &h01B61D9A, &h7C5A46A2, &hC239C262, &h9DD01B4B
Data &hB8244112, &h409824FB, &hD312084D, &h1B0399E9, &h96A87A7C, &h95A4C53F
Data &hD8517E38, &hD497DD0C, &h55674934, &h189D9C31, &h33A26F0F, &h5258AF53
Data &h7FEB1100, &hECB1E0E4, &hF0243B0C, &hF7B0E7F1, &hF54CB10A, &hB4E5FF8E
Data &h9C2654AF, &h63AD585B, &h948D601E, &h80632C25, &hDA0B0EB2, &h1D45E2A4
Data &hD0C3B9F7, &h0F585505, &hFCA3FBB8, &hCD3A35B0, &h3B6BDBCE, &hEBEED22F
Data &hC33C3DDD, &h801DB8F9, &h455BA158, &h00F3DF51, &hFBEF7F7D, &h0153ED87
Data &h39A152EB, &h1A9DC42C, &h0EC58FD6, &hA0AE5225, &h336DB32F, &hC63FBDDE
Data &h3DD4C831, &hA16FA445, &h0CA5B4AD, &h8B18E142, &hEC43AE90, &h543DBACD
Data &hA7AE3457, &h0AC3586F, &hFDAD8D3B, &h4DFB1144, &h4E64ED38, &h64C80C57
Data &h5644EE3F, &h24A783FB, &h9FEF8143, &hF98D835C, &h5AEA4928, &h22D0133B
Data &hF9D881F2, &hFE4F0EB4, &hB4D8495E, &h53DEFD54, &h19AF9A46, &h3ABB5A30
Data &h7FCA920F, &hE8952328, &h281117DC, &h9C817AFE, &h1BE54DE0, &hA7A64217
Data &h36BFF371, &hE8B5A66B, &h65E8D4B7, &hDA724978, &hEE9CE118, &h580772F5
Data &hA97443A0, &hE98FE8B8, &h73456D9F, &h680CEAB7, &hD394FC45, &h17AC8FEE
Data &h2BD96A0C, &hB138A80C, &h0698B6AD, &h6B02785F, &h89FD0708, &hE9A98BCC
Data &h7125EBE8, &hDD3D0E97, &h9B3CDFD7, &hDB64A96D, &h472F67AA, &h0179FA5E
Data &h5393E2D4, &h9A3574B4, &h20D1CA40, &h23F8E2F2, &h6829FA70, &h4656D2E6
Data &h87406A45, &hA22E1B3F, &hA2D2EAC6, &h500D71B1, &hFCEB9C64, &hA37350AE
Data &h28E378BE, &hFE8E67CC, &h92FBD6D6, &h9E4742BA, &hFDBFC8C0, &h1DC4EDCC
Data &h3406DE21, &hDB911DAA, &h9919D22C, &hC1D86C8F, &hDDB11DA6, &h5B103E06
Data &h7B533531, &h66A32F9C, &h23146E64, &h527243CD, &h8434480A, &h83D29E40
Data &hF7FA4F76, &hD41AC1AE, &h93AD0ACD, &h5583B207, &h8A3BE8D8, &h7A0BB004
Data &hC6F86829, &h53CD100D, &hE8D5A0D7, &hF007D3A8, &h3CB96B5A, &h69F37648
Data &hB6228A96, &h0A5221BB, &h6395051B, &hF03A0276, &h1A1F5C2D, &h4D774F79
Data &h22A03C64, &h1EAE847C, &hE2F37046, &hB3BC20D5, &hD232CC75, &h64F354D1
Data &hC37828C2, &hF36ABFE6, &h03743DEF, &hD81BF1BF, &h94BAADC3, &h2C72A99D
Data &hC18535BF, &hCD9C77FD, &hCB085B70, &hE8BA2340, &h0BB4C532, &h56A8FAB7
Data &h9CAB5B6C, &h25198DFE, &h276FA4EE, &hE046CD49, &hC3835A8D, &h4B7AB7FE
Data &h770C5AC8, &h712149AF, &h4AF57D86, &h70A3409B, &h13A00BFC, &h24F3BF16
Data &hFF41A4F0, &h29A2B302, &h6CB1F67D, &h8AD09015, &hDDCF0983, &hD06ABE92
Data &h5928CAF4, &h8D0FB9A5, &h4C2E73CA, &h52FA7733, &h8719E66F, &h0B36E0B8
Data &hB0DBB606, &hF90F1216, &h5DD1C815, &hE71D060E, &hAA81EA44, &hBA3A22AC
Data &h9F03F7CB, &hE5E8F026, &hDE0ED164, &h3D8BE689, &h0A56B9F5, &h2B1AB544
Data &h2D2F2259, &hC8B9CEB1, &hB858A3C3, &h93626D4B, &h0FA36772, &h37103B9E
Data &h1AE8CB1A, &hACB98FED, &hB025DB62, &h2170CBFE, &h083755FB, &h2787BC1F
Data &h2F8FB65F, &h699BE473, &hEE82DE25, &hAB70F7A7, &hE142BCBA, &h8BC22644
Data &h4AABC434, &h9C023099, &h34C4FF02, &hAAF9304D, &h55BFF7D5, &h070C84D2
Data &hCFB54185, &hFD9356BC, &hF19F7559, &hA5812769, &hBC68D2FB, &hC61838A2
Data &hE835D12A, &h6CEA4F08, &h69935E37, &hFE45CFB5, &hFA60D859, &h3320A2EA
Data &h5EFD4C4C, &hFBF3C6DA, &h5E0807BB, &hB199894A, &h3A368903, &hB2C43B92
Data &hC997AB87, &h6E5BA782, &h890661FC, &h32B68031, &h6413EBBB, &hDD79FFFF
Data &hE945EA65, &hCB75DFB0, &h8D7356F7, &h4F8AEB1C, &h5CDD3515, &hA806102B
Data &h143B9B43, &h8ED30029, &h47A3BA25, &h4D9811D1, &hAD1B98B2, &h6AF43646
Data &h0F3DA3AC, &hC4D17E1D, &h60DCCE05, &hB1CC434C, &h2F260D76, &h5A00D471
Data &h6BCCCEE4, &h11A35DC5, &hB03B6B54, &h356ED7C0, &hB3353743, &hFF8B5564
Data &hA19AB0D2, &h32F45901, &h7082B42B, &h88F2F8D1, &hFF199E82, &h8D838534
Data &hEF9AD2E1, &h46368ACF, &hE79D1DB7, &h129F2FE2, &hF692AF6B, &hA4410883
Data &h6B6533D8, &h26F01E2D, &h9EA03693, &h10CEC988, &h4C2F0295, &hCF90E5BE
Data &hC4C0946C, &hE21214A3, &h75C005AC, &h950FE3C0, &hFE929D2A, &h4CB9198D
Data &h8C9961EE, &h6BEACA90, &h9403041D, &h859F5EBF, &hA3DE64E8, &hDAFE5597
Data &h8F654D36, &h5F7AF9C7, &hA4EB7D19, &h66FADB8C, &hA6B35EDC, &h7A03B3FA
Data &h04A88DC1, &hF7D83E50, &hECC89D35, &hF7A9CE47, &h47668DDE, &hDA70852A
Data &h42CC8AA4, &h5EB2E945, &h7F5F0A51, &hBC3DBFCA, &h3EA636C8, &hFCA9CB7D
Data &hF2AC8C8B, &h447E1627, &h80FF1582, &h06A1E9A6, &h4F3CC40D, &hEEA909D9
Data &h1B3035EB, &hBC3BC32F, &hF9AB9EEA, &h4333EEDE, &h4F0236F1, &h599FB505
Data &h951DD0F4, &hDF8A5BC3, &h9AED1C16, &h37F31857, &hAE1BF4CD, &h6FC5DF6E
Data &h45E39AA4, &hEF0904AF, &h1571080C, &hFDF767D4, &h99DD2FCA, &h80AAB46D
Data &hE6676A9E, &hD2A5D6A6, &hBB6DB0B1, &h0D77B4E8, &h63AF6A47, &h3C653A79
Data &h2F08CB82, &h914BF0B3, &hFA4631F6, &hA66C8928, &h2D830B35, &hBB201A03
Data &h31C61639, &hF5CFAA34, &hF4B895CC, &h5EA44FA9, &hACE6C16C, &h4A6F91EF
Data &hCEC9180A, &h03761C95, &h5CE1B21A, &h2FEA3BAE, &h57E3284B, &hB48C844C
Data &h1E0AA2CE, &h7BC95F01, &h10D16439, &hCBB67222, &h1B004ED6, &hDBAD3482
Data &h13AB8394, &h428595E5, &hB900B64E, &h911918FE, &hAEA86D2A, &h9535AAE9
Data &h700A5D0A, &hB746672E, &hC3DBFA6B, &h3BA774DF, &hC32ADE6B, &h7A66C1DC
Data &h8E9B09B6, &h72B8D806, &hF0C8E9C1, &h24E94B00, &h772DA5D6, &h556C2ED0
Data &h441F009E, &h962B9C30, &h6EF315B0, &h1DD0C51C, &h1D21611A, &h5FA2FEC4
Data &hBB90026A, &h859F2B5C, &h9DF49584, &hD71D1702, &h22EA016D, &h046D9431
Data &h283CDD58, &h126CB4FA, &hB947F6D3, &h4C47B2AE, &h33CC8F80, &hDFC18A5F
Data &hB4D598CC, &hF759966D, &h43431AA5, &h056D5D58, &hBC5BDDD0, &h23951855
Data &h8ADED9CD, &hF05CCFCE, &h322D6230, &h65B36A63, &h469E41C5, &h8D5B2E6D
Data &h50E2AD65, &h9A21563A, &hD1EE47F0, &hCA6F49BB, &hB96FA573, &hC323898B
Data &h13E1397A, &hAAFE13A4, &h7E3A955C, &h3322D0FA, &h63AFE3F9, &hA1C0AB75
Data &h3E9D0454, &hCF46E4F2, &hC69B7F9C, &h1A10F4BB, &hAE852477, &h7ADFF624
Data &h7B587B7C, &hE26F1069, &h23784BF6, &h3D91B942, &h0F734DE1, &hFF46C725
Data &hF7EFBE5B, &h09F9BC9F, &h33FD8801, &hC67DF26A, &h0D35A5EA, &h08BB36CF
Data &h1C8BE780, &h9D332EB9, &h93B6C485, &h5C0A25A9, &h3593B373, &h6630049C
Data &hC9A25E46, &h64BAAF74, &h8923C4E7, &h37183263, &hD4F84AC9, &hCF1A734A
Data &hD52F040F, &h07882199, &hC977F7FF, &h52B70D8D, &hF44C45DC, &h6E5E8E70
Data &h3B5A6AC8, &hF18E62C4, &h65684913, &hD0112986, &h32519160, &h7DF8F720
Data &h55156FF3, &h54FE6C86, &hD0DBA1DA, &h7960583A, &h24DC1A17, &h84DF25B2
Data &hB4D7B2E6, &hEC49CCAF, &h78F3D280, &h06B8568F, &hC618FAF2, &h094335F4
Data &hCAB01D0C, &hA6E79747, &hB7A92177, &h2E6C9C62, &hEBEEF32C, &h73C60647
Data &h7C1C5F3B, &hAABF2848, &hA496E472, &h0B6B7E8B, &h5CE2353C, &hDADFC6A6
Data &h483E54D2, &h6B8956CF, &hB8F65E23, &h98F880B0, &h4B417EC6, &h95546B30
Data &h1805EADA, &h7C8A6ECF, &h96CC3F99, &hB3144F38, &hD9BD10FC, &h8390EB84
Data &h8876631A, &hE45716BC, &h7E0A683D, &h5BC9DFC8, &h77CA681F, &h1F793D48
Data &h1262CF46, &h61533A14, &h10A5CAC0, &h71CC2081, &h54C58D7E, &hEE3ACD91
Data &hF0B77C03, &h32D4ED23, &hB985E7D5, &h0C2E3408, &h1A756D97, &h444CC938
Data &h7E408977, &h9298E99A, &hDEE2DA0E, &hB4E20DF4, &h82A5EF2B, &h5C889A31
Data &h6C807428, &h21AC1E1E, &h0050606C, &h5D4C8415, &h30D3D0B3, &h82EEFE66
Data &hA3F4B472, &hC5C477F5, &h8CA11BFF, &hB3C858DC, &hA81FC2F0, &h7E4ABB0C
Data &hFEE685BC, &h723423A2, &h6F41E2D0, &h77CCF283, &hF96CFD5B, &hCF93C413
Data &hDC395F3B, &hFB3DE8F3, &hC9405548, &hD43A4277, &hB08AFB6F, &hB6537612
Data &h248CB410, &hC3C790CE, &h7C92E4B2, &h444F71FE, &h2B518F63, &hC2127E2D
Data &hBCCC5B51, &h334342BF, &h234C5D49, &hDAD386FE, &hE3F11FE5, &hB66C1125
Data &h029B39CB, &h476C5EAB, &hE70A2FF6, &h25219F99, &h3D5B863B, &h0EE4D5D7
Data &hA67EB319, &hC1DDC3EF, &h1C22D525, &h194DCA1D, &h8B7E8D28, &h92A7793F
Data &hB949CC95, &h7FD4AD76, &hDAAA2D77, &h77BF7A41, &hF38C460C, &h3294F60A
Data &hD00A34D1, &h96403181, &hADF8F9F5, &h397F5050, &hBD38C7B3, &h2EF59A6E
Data &h2BC7CCA7, &h295D945D, &h149E580D, &hDF82A5E2, &h3A3E7A43, &hCC1941AD
Data &hAB7FC0C1, &h81618B4E, &hCDEDBBD3, &h1FC9F25D, &h3EF57D18, &hCA75AA68
Data &hA703BD97, &h0199EF1E, &hF83466C5, &hCA91811D, &h541C5B5E, &hB7F75B31
Data &h4A8C6B7F, &h79C94CA5, &h6F41C99E, &h1DE85788, &hD50EE688, &hB1AF890A
Data &hC965968C, &hC1EC4DFC, &h9B3ACCC2, &hA76EB998, &h97EB0774, &hEB30263B
Data &h4780AAEF, &hD0F8CBB8, &hC2678870, &h2E13A9D0, &h1A1F4444, &h1E3A4033
Data &hBC25083F, &hD643324C, &h8D4C0496, &h2A64902D, &hDA45096E, &hE4033B22
Data &hAC3AE026, &h922307CD, &h151E0728, &h57D6937B, &h0F95042D, &hC6ECCE7B
Data &hDEDCC7EA, &hEC9CFA31, &hFB49D3ED, &h76881C02, &h2C03BB71, &h6EFF774C
Data &h075B0EEC, &h8CA625E2, &h78A9D63B, &h800BA987, &hDD611C6C, &h34989243
Data &h6B64FBDE, &hF40811D2, &h51191E07, &h5E471A29, &hB885DBD3, &hF8452C91
Data &h4A2F9D12, &h06AEFAAD, &h89D9BEF1, &hB2C10B5E, &h3CC7CD14, &hDBB36C29
Data &hC60BF5D6, &h7088B055, &h896B2F8E, &hB2459CA8, &hBC337354, &h6F47DC8B
Data &h2A2842AD, &hB006EB12, &h4F9EB394, &h6B0E69D3, &h79F4E523, &h92A231A6
Data &h04680634, &hC55D2C71, &h3413DA8F, &h6D45AB01, &hE96305ED, &h17F0FA82
Data &h61AA5D17, &h6912305E, &h0B6F8A3D, &h03B22E68, &h06A49BC0, &h086658F6
Data &hB5D56C0F, &h468D125B, &h8CF3EE5F, &h3FFF9A8F, &h20988AFF, &hB9EB2255
Data &h737B2BE5, &h3307AFA4, &h391AF2A6, &h3DE79CAD, &h03115FB5, &hB8121582
Data &h31C13D57, &h4F69F25F, &h5B80525D, &hA03E0428, &h8056C9C9, &h02B685BA
Data &h530CA22C, &h5BDD5F51, &hA674A847, &hC05D6B4E, &hF91301A9, &h13EFD22C
Data &h855A9800, &h4AF1956F, &h86DB2751, &h0C41395D, &h0F0197F3, &hB1DE8AA0
Data &h8FC70E61, &hE0C95924, &h16CBBB2C, &h619BEDBC, &hC47ABA8B, &hDB8C75C6
Data &h92E961A7, &hD5748A68, &h28B3424E, &h7317E88E, &hCD1DED50, &hB3ABBC50
Data &h95DD9CA8, &h24A85F05, &h7136B252, &hEF3CF634, &hD7C62E26, &hA2578568
Data &hD44F8AD9, &h4E74E4B4, &h1CA2258A, &hD4C4C412, &h2FCC3AD6, &h32ACEE23
Data &hDECEE665, &hFD93750A, &h36ABD081, &hB956EF2B, &hB961394A, &h27D6A7EA
Data &h57D219E1, &h1F32E843, &hABDB9F1B, &hBF73FAE8, &hDA1AABF6, &h4742D0CA
Data &hA3A986C1, &hB6A5C24F, &hBA10B353, &h161073CD, &h94CC1421, &h862F13A2
Data &hB3155C45, &h5D6037A0, &h2C9E4151, &h3A289CB3, &h154CB365, &h76F1760A
Data &h841066A1, &h0D24A15F, &h9A46F448, &h5E724D5A, &hB6E24EFF, &h2EAD9A97
Data &hF3775873, &h4184D659, &hCBF3B52D, &h78454BE5, &hB8884722, &hD1800CB3
Data &h911986BD, &h8FEE7819, &h51C27C90, &h30FC3AAA, &h5BFB4B0D, &h2729079E
Data &hBF2C3506, &h5E61DDDF, &h9967F572, &h0AFAEBFE, &h2494D1BE, &hA287C982
Data &hB28A4519, &h56BFEB1F, &h35491EC7, &h6A13156A, &h3A6F5719, &h505031E6
Data &hF801E19C, &hA2349F7B, &hEC002E8B, &h7BFD8078, &h29EEC116, &h1BAD6FA9
Data &h29FD36AF, &h9ECC602E, &hB6C77647

#If NUM_DWORDS<=10382
   restore BigFloat_exp1_bf_data
   for i as long=0 to NUM_DWORDS
      read exp1_bf.BigNum.mantissa[i]
   next
   exp1_bf.BigNum.exponent=&h40000002
   exp1_bf.BigNum.sign=0
#elseif NUM_DWORDS>10382
   restore BigFloat_exp1_bf_data
   for i as long=0 to 10382
      read exp1_bf.BigNum.mantissa[i]
   next
   exp1_bf.BigNum.exponent=&h40000002
   exp1_bf.BigNum.sign=0
#Endif

BigFloat_pi_bf_data:
Data &h1921FB54, &h442D1846, &h9898CC51, &h701B839A, &h252049C1, &h114CF98E
Data &h804177D4, &hC7627364, &h4A29410F, &h31C6809B, &hBDF2A336, &h79A74863
Data &h6605614D, &hBE4BE286, &hE9FC26AD, &hADAA3848, &hBC90B6AE, &hCC4BCFD8
Data &hDE89885D, &h34C6FDAD, &h617FEB96, &hDE80D6FD, &hBDC70D7F, &h6B5133F4
Data &hB5D3E482, &h2F8963FC, &hC9250CCA, &h3D9C8B67, &hB8400F97, &h142C77E0
Data &hB31B4906, &hC38ABA73, &h4D22C7F5, &h1FA499EB, &hF06CABA4, &h7B9475B2
Data &hC38C5E6A, &hC410AA57, &h73DAA520, &hEE12D2CD, &hACE186A9, &hC9579300
Data &h9E2E8D81, &h1943042F, &h86520BC8, &hC5C6D9C7, &h7C73CEE5, &h8301D0C0
Data &h7364F074, &h5D80F451, &hF6B8ABBE, &h0DE98A59, &h3BC5797E, &hD2AB02E3
Data &h0732A92F, &h9D52AD5C, &hA2BA44C3, &h131F40A2, &h02AE51CB, &h51555885
Data &hB5A662E1, &hA08A0F46, &h750AA435, &h7BE3974C, &h9D9F70A0, &h8B1B7DE1
Data &h515D4E2A, &hEBA0C18F, &hB672E1F0, &hB4DC3C98, &hF57EB5D1, &h9B61267A
Data &hE3D1929C, &h0944AC33, &hB9DC7A44, &hC35A5DCD, &h7E25FF40, &hDB31410C
Data &h9B0EC04E, &h67D90D4C, &h8A43E563, &h02EF6401, &h977C22EA, &hEF4C2BAD
Data &h8EE13118, &h175B28DC, &h411C49F4, &h0E9CB566, &h287B6B7F, &h9C1FA211
Data &hC9705A24, &h15242100, &h234E4782, &h54F0FCDA, &hF10E3342, &h17B74B64
Data &hD33864E3, &h0D5E9C47, &h83528D06, &h96C2A17B, &h44B07D39, &h455A899D
Data &h1B77785B, &h609BD1DF, &h25D1DF82, &h83F7D954, &hC50F8B28, &hE9CD780B
Data &hB33652C9, &hF4121874, &h44677430, &hCA2B7CFD, &hA3EC252E, &h19DC5AF5
Data &hF7037BAE, &hC42E0903, &h9A00D224, &hFAB60B55, &h32769D53, &h11B1FBB8
Data &h30DFF6FB, &h9214D811, &hE9BE86B9, &h26805092, &h46D87F56, &h9A4F8E04
Data &hD83A9B96, &h4C04C8DB, &hD92EA3CE, &hC7B746F7, &hBF1FF280, &hD5B3CA61
Data &hDCBB6705, &hE8260035, &hD60D4A7D, &hB204FB06, &h22F2E4F6, &h10CB5123
Data &h1B47DB7D, &h79F3629D, &hA899CD97, &h59DA9763, &h7B6FE288, &hFCD984A9
Data &h66640A2A, &h257AF5E8, &h4DF71E80, &h26F19A57, &hEB307940, &h38C9725D
Data &h9E065D42, &hBA2E43A0, &h7E905AF9, &hCDCE9FDE, &hDAABCE05, &hE8D30190
Data &h56B50806, &h32016393, &hCB3CF92F, &hF7D8FD1E, &h64752F4F, &hC6D99117
Data &hC1E3A8B6, &hFFEB0B58, &hA97A80F6, &h45682A95, &h5991EDAF, &hD7E91C3B
Data &h02998BDA, &h41F006FC, &h14F2E2BD, &hDE537C65, &h00D43AB1, &h76F8BB4E
Data &hDEAA1547, &hB143F7FE, &h1D633996, &h34627AAB, &h9B4AD93D, &h85DE52C6
Data &h470FFD1A, &hEDC7808D, &h0087D1EC, &hC7E90C1D, &hC257E5AB, &h616E8E9A
Data &hDCD29F23, &hCDB7C22B, &h2E94724D, &hE25FDCBC, &h870EEF96, &hD5265BF1
Data &h9B17D89A, &h0E772637, &h47790656, &hD1B3BA60, &h0E83F4F7, &hF15F88FD
Data &hA4AEDED2, &h6D74848C, &hC7556C73, &h8B5C9EAD, &h0684768E, &h857E392F
Data &h0471E2D9, &h7C73ACA5, &hBC7FB717, &hDF90915B, &h244445C0, &h94806F80
Data &hE27D6AF5, &h03447E18, &hE68E7F8C, &h8D9D460D, &h69797910, &hC5F070BB
Data &hBF53A96F, &hF45810FD, &h0F2D0660, &h7DAB7BA7, &h40C5679E, &hB6744F14
Data &hCDA5427F, &h07E89F05, &hBBE621DC, &h0E956D46, &hC8B2FD13, &h3404ABB8
Data &h2C9E6398, &hA108D0A3, &hBF356903, &h2BBDAFD4, &h363AA217, &hAFDCE9AE
Data &h7F5E6D78, &h63D9F44D, &h06B208DE, &h9D70F3F2, &h48012871, &h69038D9A
Data &hF1134005, &hDABDC705, &h792321B4, &hDF804DC8, &hF2AB1C88, &hEACEFD35
Data &h53C60A1C, &h4ECAD29B, &hF903EADD, &h10172DCE, &h2C19301B, &hB314AE7D
Data &h488E40CB, &h42739A52, &h0D9A396E, &h53D8A54A, &h50DA8802, &h94D29948
Data &hAEB07AB9, &hFDE4DE37, &h215B0523, &hB40F33A0, &h0045D37D, &hAAB8DF48
Data &hFF94B763, &h59506EC8, &hADB31B29, &h0F3DCFCD, &hB7F9A029, &h762C2AB3
Data &h229D816A, &hED4CFC7D, &h0845D23C, &hCB74283B, &h525BD387, &h4DAD994A
Data &h26DBA849, &h7620C931, &h1D6B7535, &h824D3EFB, &hECE77305, &hC47F6D93
Data &h37655463, &h8B4CD0BF, &hFAB32293, &h66158CF7, &h08C9B015, &h2BA84A61
Data &h4D02C89A, &h0720C1D1, &hF1FAA4C4, &hD2DA14EB, &h2B5C7F26, &hB4CFB9FE
Data &hB50E94E0, &h3F7F4187, &hAA6969C7, &h37812AEE, &h0A66E904, &h34238759
Data &h331C174E, &h3010F662, &hF04B4359, &hF9F5D77E, &h49E4B8C0, &hA35B5385
Data &h0B43F9AC, &h22950714, &h35BCE298, &h2D528039, &hB9F03C20, &hE3FEF572
Data &hE473EA27, &h62B8B795, &hC581D6D1, &hBF828060, &h6F80E0F8, &h2010059F
Data &hFD7067A8, &hD1E5ABA5, &h912C1BD2, &hC6E0490D, &hEE8C889F, &hCBE5497F
Data &hB4A1923B, &h9917AA38, &h09D72F2C, &h09BE16D6, &hE645ABB1, &hA4D79EED
Data &h3D4A230A, &h307E8018, &h77664639, &hF523A8F2, &h0F11C66C, &hC9DF5071
Data &h799405DD, &h08C1F599, &h8A72A459, &hC27B6DC8, &h437A1068, &h1FB05025
Data &hF965C094, &h8124BBE3, &hCAB3CD83, &h95E57C4D, &h7EF4D3B8, &hFECC9840
Data &h859C5D70, &h96E679F9, &h72A89390, &hF9735B89, &h2280D6EF, &h34FC266C
Data &h3BD2C238, &hC3A046D0, &hBDE4FCD5, &hE74A5BEC, &h6763D761, &hD6DC28EF
Data &hD3184A1B, &h3623261E, &h9778E0C2, &h3990AEC8, &h46EA19D9, &hB92615D0
Data &hB0950A6A, &h19532E22, &h8A84A000, &h1099D726, &hEB8EFFC4, &hF0818A72
Data &hAC0D63BE, &hB2F888CC, &hD821AAB7, &h8EBD1E3B, &h59E088C1, &hDAC92528
Data &h4F947F37, &h6CBF8FDF, &hD4F5D5F9, &h60F0A9E3, &h74371A2B, &h87574B7D
Data &h8C3072F0, &h52D1F155, &h9BB8FF38, &hE271E837, &hD14B2EE5, &hCCCF38E8
Data &h7C01F44E, &hB2933641, &h2972664B, &hC4E0859B, &h5630A875, &hD4A71753
Data &hC52FE1E2, &h98F0516F, &hA797BA75, &h39B0E959, &hE8C9C930, &h78CE13CB
Data &h02911D38, &h47B89895, &hB75D6FF3, &h775618FB, &h371DE22C, &hAD33DE44
Data &h1D8BF9BE, &h880C67F9, &h461996EF, &h7DF362D5, &h2B2AC10C, &h2B455CC0
Data &h17767528, &h7ED97CA9, &hD9577BED, &h6ADB717C, &h20A90DB1, &h41483B0B
Data &h8766EA3B, &hAB0CF8A8, &h809E6541, &h875B0DEC, &hB019A7F0, &hF5501B1E
Data &h7DAB9AE4, &h82638511, &hCEACF4F0, &h5E5D56F0, &hA7766435, &hE3031165
Data &h3CE55AE5, &h5D979C23, &h732458F5, &h78CDEF86, &h55011B4D, &hCB2AD5DA
Data &h820342D1, &h91E155A5, &h998CF74E, &hAE010DC7, &hBCDAA058, &hCC3AFD04
Data &hCCAFBCCB, &hF311EBED, &h47C1BC44, &hD4BF196B, &hB88F6C9A, &hF8B34094
Data &h0871AC41, &h4E3F30FE, &hB4B6F6FD, &h0BC2C5D4, &hCABFAC25, &h28D91393
Data &h1CDC1E1F, &hF8D61234, &hB66D9857, &h5A997182, &hA47ECA47, &h236DE189
Data &h42C75F97, &h79A637FF, &h57F1476B, &h0F73E1E3, &h9AEA50A6, &hCF4325BF
Data &h1A1082E8, &hA101F09F, &h022F7715, &hB51D555F, &h56DB6278, &hAFD65A7E
Data &h863A17A2, &h177B55DD, &hAB2A79D8, &hEA0E6908, &h2EC0F3CC, &hF4342A6E
Data &h3F225A3B, &h51EC0B12, &h867B150F, &h92DC6932, &h37E4441D, &h060E3DB5
Data &h1BF8A926, &h1B4E5BA4, &h923C2450, &h5AB49594, &h284ADDF8, &h0568CA44
Data &hE8A3158B, &hA11C1070, &h02C21469, &h5062AFAF, &h50ED6FA1, &hF119FB83
Data &h099B9784, &h946C9BF2, &h0EB2FF67, &h8B6111DE, &hDBE6F1BA, &hCE5F73A3
Data &h02042F95, &h3E73B993, &h75303C04, &h20CFC284, &hF7477EC2, &hAB0ECCB9
Data &hAD4B4D3D, &h56286036, &h12D0255F, &hE4005E56, &hE4F223D1, &h761A29A4
Data &h27EEAB38, &h2870F4F6, &h4EDB9EDE, &h9882AC46, &h6B3AFED3, &hCF1B3A1A
Data &h062E21A3, &h2B89F1C6, &hC1E947C4, &hF78B6FF9, &h00A9F10F, &h3C7D81EA
Data &h57371CF9, &h5EDC1D6F, &hBF49EAD3, &h44A40A07, &hBFB26130, &hE4A34949
Data &hA208A907, &hBBB016A7, &hBDE7A359, &h76A51003, &h46A04123, &h899907A3
Data &h521DBEA5, &hBA80030D, &h78F1CFB1, &h74B9222A, &h30A10A7B, &hA5FC5C42
Data &h026CAFE0, &hECB5AC8D, &h7B87A6EE, &h9B35017A, &h2DFDE04F, &h601DECBC
Data &h2BFD636E, &h818E5C28, &h24B7593D, &h9AAFE9CA, &h0ED12A3F, &h355E5054
Data &hD14283C1, &h2A98214F, &hA0516436, &hD74DB36F, &hDB46E0A3, &h16BA4348
Data &h03407605, &h213D0C6F, &h7279FFF5, &h17443D6C, &h65AC6700, &h33D7A6B5
Data &hB55670F3, &hE699BAFF, &h6673C51C, &hCA035952, &h1107F4F1, &hAECF9C2D
Data &hCF71CEBD, &h59D89274, &h58EE4FD7, &hBA5B68C2, &hB1351B31, &h8F571CBD
Data &h91D377D3, &hA6EADA19, &h93420F3F, &hBE53C107, &hDFD857AA, &h76C7F59C
Data &hBA2A02B5, &h65D244A9, &h3AAA99D1, &hD1041C6C, &h3FF35D4D, &hBE84B4AA
Data &h5AAD433D, &hE508ACD2, &hC665494B, &h1CCF0ED9, &h9D315252, &hB1F9892F
Data &hCAF7A3F0, &hE481498B, &hE7EFC740, &h1021397B, &h8405D8AA, &hE0294167
Data &h1CAE08AA, &h47263369, &h12460899, &hFE387C36, &hE03FCE4F, &h720820F8
Data &h7A023BCD, &h22EC4370, &hB992FA8F, &h5EACDE06, &h8F95E60C, &h7A0889AB
Data &h212BDBC1, &hA30154E3, &h06FFC745, &h18FB1B60, &hD87095A6, &h10170994
Data &hF57B327E, &h8E568C08, &hAB591CAF, &h0199F497, &h09D9205B, &h1775F5C9
Data &h142D9510, &h7735D06C, &hCEF39064, &h616D17B9, &h468093C2, &h2CADBCA7
Data &hEB23E843, &h173E67AF, &h82A24D1B, &h7C3BEA47, &hD61CEFE9, &h3F99F468
Data &hF0523B1A, &h0CC977FB, &hA1D37B75, &h5FA7C7E9, &hBD4096E3, &h050F5EEF
Data &hC4C8DF0A, &h66DB7358, &h6E33DAA8, &h836B3961, &hB93B2EA1, &hDEE68740
Data &h2789486E, &h3E6007FD, &h1DA9C87C, &h93487F68, &h5B33DCFF, &hDE76DBEC
Data &hE5048E78, &h5EC8AAF5, &h1DD8997C, &h428ADD69, &h23DCA3CD, &hFBB1DEB7
Data &h59B9C975, &h9E608ACB, &hCC013714, &hBFA17189, &h6B42156D, &h3E335159
Data &hD893AA66, &h63C17788, &hE3509211, &hBDBC928F, &h38350DDF, &h325FDB1A
Data &h80D35880, &hC08E576F, &hD1E92DEE, &hC7170E1E, &h4A2210B2, &hC850909C
Data &h36C86763, &h76AD5F51, &h53257B3A, &h76D43542, &hFDF5FF4C, &h4327261F
Data &hF4EDE402, &hBF87BE04, &h3303C3DF, &hC3001B02, &h6E8FEC1A, &h37B1C0FD
Data &h83BA2D70, &h26B9B7E6, &h641A1359, &h9F80F55B, &h8D84020C, &h39E002F2
Data &hFBBD02BD, &hF5EF4571, &h22AA3214, &hCDFAC173, &h0A72C7A4, &h7F96EFED
Data &h17A3A779, &hC43C4DEE, &h129B37CE, &h1E459C73, &hA5A3AF92, &hAA37E6CD
Data &hCBD75933, &h0C58EEFC, &h24235073, &hCC8AFCAF, &h123372CC, &h7105A2BB
Data &h8466AAAC, &h8E4816F2, &h65C85D67, &h0DDC102E, &h808D4312, &h43ABA54C
Data &hF5BBF8CD, &hB7054EE0, &h4B31684D, &h0E219231, &h9F42D0F8, &h104F85F4
Data &h6254CD01, &h28EB77F0, &h80D5C9E8, &hE85D2D26, &hFD0C3790, &h7943478B
Data &h4EE5BED4, &h1AB9C837, &hF50F1674, &hDA7E6BFA, &h92808AF0, &h0D38341F
Data &hD50015AE, &h206F3681, &h3CD7C461, &h3BB9FC32, &h0E1B0260, &h330D4035
Data &hAF80BBD1, &h4607AC37, &h000302C5, &h5186E3EB, &h108F34F6, &hB919C753
Data &h1A9E16EC, &hA61610B1, &hA5DE5F72, &hB485E5B6, &hF75FE3ED, &h0E72C8EB
Data &hB3782F20, &h4A5BE00C, &h41CB9051, &hEBE493E1, &h24371B92, &hFB926CED
Data &hC8D60ADD, &hA69CF5C7, &hE76AA2AB, &hC047E52D, &hAEC1EBE6, &h9A6D687E
Data &h20F2877A, &hF58B0F37, &hC51428A6, &hCB628899, &hE37EAE3F, &h3AB70A76
Data &h21B155FE, &h76EE3641, &hBEBCD191, &hA4931C10, &h933877D4, &h72030007
Data &h01D1CE71, &hBE9FD7AE, &h7D5E13B9, &hBAD62968, &hDAE5833C, &hF27D19BA
Data &h169C113A, &h04CDE4DD, &hF6A88C74, &hEDF87B98, &hAEB168E3, &hF6380623
Data &hDDBC60DB, &h590D0C82, &h2D93758D, &hF351B375, &hA2BA4559, &h7DE4A373
Data &hCE351BB6, &h932A4E16, &h42987FC7, &h72346EF3, &hEEAB9850, &hEA66826E
Data &h3149CDDE, &hDD4DD232, &h8564A937, &h45F2F718, &h250FD6AF, &h83516A8C
Data &hD31F7C67, &h14D43771, &h16044E15, &hC2192177, &hB528F01D, &h54E79685
Data &h241E030D, &hD4DF4B52, &h6C7F28AA, &h85D322DE, &hB1413517, &hCD39D1D7
Data &h0A5D4CAC, &h377AAB17, &h4E397F7E, &h9FBA97BE, &hD1F8237B, &h4BBFD052
Data &hCC072548, &hAC3D8430, &h0CD84F35, &h69D9F72C, &h9F4C87EA, &hD4F1A6BC
Data &hB96785BE, &hC8115C5A, &h8CB6AD61, &hD00BED33, &hEE8E79F6, &hB3E3E969
Data &h40FCF92E, &h7D6F95C4, &hDAD6B5A3, &h92D447AA, &h67014D63, &h8F00CD2F
Data &h323D8567, &hEF6C9FD4, &hDF469E24, &h6941DABE, &h67C6AB31, &h4BC89971
Data &h43C2F80C, &h8F6BAB02, &hAFBCB072, &h271E9AF4, &h60A82B6E, &hA447A36D
Data &hD01D0B09, &h282B2785, &hEE1F5CF0, &hA9E482BD, &h14B938D7, &h6549D039
Data &h50D9FB6C, &hD8F3190F, &hAFACE337, &hD936E798, &hCBA99EC9, &h458AAFEF
Data &hA81AB1A4, &h1455D1E5, &hD9428BB8, &h8E1056CF, &hC55E628B, &h3E656C92
Data &hFA6F40BA, &h89C186E4, &h71BCEAC3, &h149907CC, &h8F53D486, &h17D9F3DE
Data &h72890E73, &h23BA7DF1, &h9545B71B, &hF61949EA, &h3246F29B, &h4B209F34
Data &h05157040, &h86EB6D91, &h234C296F, &hE848390B, &h359CD230, &h53222E06
Data &hEAC366F6, &h78E10645, &h72DDF7BE, &hE8DAC46A, &h0666900B, &hFB5DA71D
Data &hDEED1353, &hF1D2CFFA, &h29F1A852, &h25E5A66E, &hAB975675, &h47D32425
Data &hDC6B3095, &h75F9E37A, &h3E94DF23, &h1AA17AEC, &hF57613B8, &hDFB2731B
Data &h83A0706C, &h6F3AD89A, &hBFC390B3, &h8D7A9BEA, &hEA020658, &h4275A716
Data &h61A69233, &h5008AD7C, &h270D8021, &h44ACC1D0, &hE835C4FD, &hA6737502
Data &h4379F9DC, &h11A9055C, &h1008D0EA, &h593B913F, &hC308AB05, &h8F3C99FE
Data &hE5D9D3C9, &h59A2292D, &hED0441CF, &h0A8E73CA, &h5979964D, &hBD00FDD6
Data &h4F00E643, &hF5E63E8F, &hB678088E, &h1D0F4556, &h38D4843A, &h4EA27DEC
Data &hD686D6F6, &h5EA856D1, &hC019CE19, &h563489B3, &h3C6FC98B, &hE705895A
Data &h7FBCF2CD, &hBA1FADD9, &hD796A8CF, &hF93ECA2C, &hE5FCB911, &h60AF37E1
Data &h507C8FE3, &h8CDCA0A9, &h2FD72C9B, &h0E75B4E7, &h5E154322, &hC895D546
Data &h8DB6083A, &hF7182B50, &h60869283, &h2E581D22, &h17076370, &h70B4C6D9
Data &hDA64C505, &hF193C74B, &h24F8FCA9, &h97069C96, &hFE9D01A1, &h5C4B8F90
Data &hF0D853A2, &h0A5D19A4, &h662DF389, &h061BB196, &hC6F9ACFC, &h6CDCC979
Data &h77305B7A, &h387F1F88, &hEF2A66D2, &hA0F6D6C4, &h8E7313CE, &h7E69F3F3
Data &h78B0C58B, &h37E960E8, &h2C247E96, &h2FB7D914, &hCFA91F9A, &hBD3193B1
Data &h1C9D41A9, &h8AB66668, &h1567840B, &h12D3AF5D, &hAB70B1B4, &hBC46939E
Data &h66F4B314, &h940DCA4E, &h82628480, &hDB8E32B0, &hA736363D, &hE993D0A0
Data &h522F0E80, &h361F93DC, &hD64D529F, &hEB154078, &h05D92DFF, &h11ADEE97
Data &hB3889348, &h2D902011, &h15B65E7B, &hE66BB4E1, &h5A9889F6, &h00B2071E
Data &h99C55DEB, &h012A3D6F, &h85D1C104, &hE7BA3673, &hB3BD7D0E, &h2903AB03
Data &h042E5FF2, &h7457446E, &hC3D557CD, &h8267CD53, &hF0CA4612, &hE017DC54
Data &h600E1B57, &h26B75F0F, &hCC86A7C3, &h4D32E6F5, &h01F84929, &h6E104734
Data &hFDBA7309, &h9673BF12, &hDABC7EFF, &h19D61B97, &h35C1D658, &h110011CB
Data &hD37637DA, &hDFFE7EA6, &hEA65FAF6, &h8FA1FF2C, &h11F7A741, &h1968A957
Data &h8738C64B, &h82CDECC1, &h00FA54EB, &h173D294D, &hD44F0924, &h69DFC432
Data &hB6288A68, &h75E26770, &hB01A6C51, &hC90723C4, &h174D747D, &hEF1D5EE0
Data &hFB6D28F2, &h92ED95D7, &h080FC373, &hD36CE345, &h493847E6, &hC949E5E0
Data &h6581E437, &hC5456961, &h78021277, &h5E565A29, &h6C4E638F, &hE6ACE3FC
Data &h8BF83115, &hE36C5045, &h8C1A6909, &h93442654, &h171D565F, &h9BBC3797
Data &hD1655B71, &hEE729AD6, &h8F905630, &h3E35C70A, &h7AF5A1C4, &h73BA80A5
Data &h332B332F, &hBDB2521F, &h25D1C1E8, &h0D972083, &hCC7594C3, &h7C84F065
Data &h20FBD9BB, &hB9609301, &h84284438, &hC6273E8D, &hEA032FFE, &h741C97EC
Data &h5551B689, &h5DA6464E, &h84CA7D85, &hB8A7CB40, &hC7CD29CC, &hC5050BC6
Data &h31342540, &hF4574B97, &hB5C212F5, &hB3D14EA4, &h32A8DEB8, &hCD79960C
Data &h4EA8A2A8, &h2EE40EA9, &hF2421276, &hD5BCB77A, &h35024C78, &h1B33EF76
Data &hF01D6055, &h9E24BB99, &hEA98B544, &h8985447E, &h64B02220, &h56775C49
Data &hD3B92DC1, &h5870F7B4, &hE98152E4, &h773DC26F, &h7AD18D84, &hB64F5FC4
Data &h6A896BC4, &h73F20017, &h743F0157, &hB61AC50D, &hD81746BD, &h7EFCFD87
Data &h3BC874A1, &h51D9E0D5, &hD637FD3D, &h7CEFBCB7, &hC990DDCC, &hA00BA545
Data &h476910B1, &h667F8DDC, &hCED546AA, &h8D26AF22, &h5F66EF1F, &h65406E28
Data &h481C9F77, &h939291E9, &h8EA471D0, &hE11275B2, &hF302961D, &h21084E19
Data &h7829771C, &h476CFBF5, &h4C8E317C, &hBBBDAADD, &h00A865E5, &h19D76329
Data &h2EF98C1C, &h1A1D4E71, &h349B156C, &h5809A0A0, &h5C6FAE7C, &h08F4FFAA
Data &hC8B3F82B, &h21C097A7, &h02C45295, &h865DC74A, &h277AD8B5, &h1B9E276D
Data &h0BEFE7F7, &h57AA5E5D, &hF43B9F1E, &h96298EE6, &h82AE2339, &h4A93BA79
Data &hD2BE535E, &h0233E9D1, &hD923BC21, &h2DBCC8F4, &hD6EC12E1, &h37229647
Data &h77E566F0, &hF42419D7, &h9B0908E8, &h18B99609, &h8E656D92, &h3F3035F4
Data &h638959CF, &h8C45A779, &hC9D4FE6E, &h2E2BAA8B, &h48FFB4CA, &h79CC14E5
Data &h80880B2B, &h999A1E5F, &h5B0E9E85, &hA2279857, &h7D45739B, &hA951D0E4
Data &hEDA5B848, &hA6B55928, &h6429DB99, &h424AFCA4, &h7E95276C, &h7367BA8F
Data &h261905DB, &hAECE5505, &h9C5D2B13, &h12742581, &hFF75403B, &h73A503FF
Data &h2C01CF00, &h61B7FED7, &hC01B989A, &hC5CF338D, &hCED62670, &hE592D887
Data &h6A6E9EAD, &h8FE795A4, &h0231A7AB, &hC92F5620, &h054D62AF, &h53944996
Data &hF83020E8, &h2AE98FA8, &h1629CE17, &h195C4ECE, &hDADE6054, &hC602DFEB
Data &h78D92831, &h11710DF0, &h7304B9D8, &h2766AA53, &h3DAA7F31, &hC5376B30
Data &hACC0D488, &h52EC9494, &h6D637E34, &hBF39E31D, &h6A2B76FA, &hFA2BD40A
Data &h2A8C3AD3, &h266984CF, &h8B4DAF8C, &h54639F70, &h5AF2B9B4, &h7B63CFA5
Data &hDBD2CAC9, &h3555A4F6, &h345647E7, &hDC00B65E, &hDC5DE0FA, &h3B4C1638
Data &h8C2E3ED3, &hD2C408A3, &hBE6B3FD6, &h8EBB26CD, &hA640814A, &h82E684ED
Data &h28DD8F8A, &h3CA8B3EC, &h001B3823, &h6D78ED65, &h0D1123D9, &h188980D2
Data &hA3C8ECCE, &h33D27DBE, &h793BA24D, &h204F2BA4, &h91AE4D2B, &hF2F3FA80
Data &h55CD3154, &h56A92153, &h5D099BC2, &hCCE6D19A, &h30A43A02, &h3A1945D0
Data &h475C0EA8, &hF992444B, &h54003EC2, &hE87B746E, &hD41285ED, &h7E717702
Data &h144BF701, &h12F801B0, &h91DD0C7C, &h81318A03, &hB3C1201A, &hD1DABF16
Data &hAC73C576, &h8F486E30, &h04860AF5, &h312304A8, &hCDB9761F, &hC331EEE7
Data &h7F7ABA11, &h90CA0CAD, &hB1064901, &hFFCC9B80, &h760D2253, &hE5D76F4A
Data &h0FCC56A6, &h27C7A1F9, &h378306E8, &h4075CEF8, &hECD99B0C, &h42AF75B9
Data &hA362B686, &hA19D06B7, &h20C1442D, &h90ED7DB0, &h8F826A37, &hBA866E5C
Data &h8A03DA39, &h9EBD159A, &h18134D62, &h95A903B9, &hE464885C, &hFBB4072F
Data &hB63CD6C3, &hA7ECBE7F, &h36F5BC7D, &h993CF715, &h0BA14338, &h299B22D5
Data &h2AAA21C0, &h4278FE46, &hE08B6620, &h16A78A30, &hBB0C1E6C, &hF708EADC
Data &hF0CAE929, &h1F797C70, &h3EC1B3B3, &hE22408C9, &hC569B364, &hFED58032
Data &hD962DEB7, &hB31FBE88, &h73C8825E, &h8EBE1F24, &hBA196E82, &hB4997C79
Data &h043C012D, &h3847481A, &h3E6D6109, &h03A9D190, &h0CE35F0F, &hE81FBD99
Data &h5855C28A, &h86BAD478, &hF47DFB87, &h670633EF, &hCB8F9287, &h20D5DCDF
Data &h81F8BF88, &h476DFEE3, &hB1BEE6AA, &h5246672B, &h84008DD9, &hAC5E385F
Data &hDC0CA7C8, &hDE840B58, &h82D9FF32, &h0AE362EA, &h11CE81D6, &hB3440E61
Data &hDCAF695D, &hD4D96FB3, &hBBEDC02B, &hF070D183, &h54E39D91, &h587B7D72
Data &h60A3B992, &h742820E4, &h518F8D98, &hE581FA99, &hC1D1F387, &h801DED1E
Data &hB90A83E0, &hB4C87E06, &hE7624758, &hDB72D53B, &hBCEE3F2B, &hA864A487
Data &hE745B85D, &hB4E12316, &hF2C7CEB7, &h1436486C, &hF1C9CAA5, &hEDAF9527
Data &hED0E56BE, &h336F6FE2, &h3A332694, &h28A71081, &hC51A572D, &h30664414
Data &hA936BA44, &h2442D3ED, &h5558712D, &h571946D6, &h79EBAE52, &hE498AD83
Data &h8D47C353, &hD434D151, &hDB9E1224, &hB371941A, &h5923EF71, &hD59D1F08
Data &hC071F432, &h5C2B1CEB, &h144599B1, &hFD9D3B3F, &h2A5C23DA, &hF1CAA040
Data &hB3A9C6F4, &hBA0D86B6, &hC76BBEB8, &h83B1B5CB, &h67ABEA62, &hD90337FD
Data &h98BC3BFA, &h4FF823C6, &h93ACD789, &h607326E7, &hC2A3DACF, &h893DE761
Data &hE8C6742D, &hC420C7F0, &hA783E7B5, &hA52C13F6, &h0F69449E, &hF452FF34
Data &h5A70896B, &h9A3AB966, &h5D7C333C, &h0017316A, &hBF14CA76, &hBD8E3F5D
Data &h200D569B, &h01A387B2, &hAC78DD8D, &h0F4FE3F4, &hCCCAB395, &h8517D2B8
Data &h10ADA6F1, &h52791844, &h6797CBF6, &h49C2B438, &hB30D27FE, &h67A0CE78
Data &h8E67D65E, &h75DE5147, &h1BC26EA1, &hF08A86F7, &h1DE8305D, &h04111E1E
Data &hCA5ED1C6, &h3C6CD3AB, &hAA6003F6, &h055AC77D, &hDAE6143E, &h87832752
Data &hE42E01B4, &h55795690, &h9875561E, &h6E73A012, &h0FD801B1, &h15FD5255
Data &hDAC1DAC4, &hBB154B50, &hD68363FA, &hBFFA9F8A, &h26EB3F82, &h268E1414
Data &h145ED01C, &h42A46826, &hA2726D59, &h6D8039A7, &h76A37420, &h4377E715
Data &hE9CE4FD8, &hDA844C40, &hAE33F3CE, &h24FEF6F8, &h2886D059, &h57C59941
Data &hC83648D7, &h83F9279D, &hE7D883B0, &h65A4F842, &h869664BE, &hC76319CA
Data &hDCED98EA, &h153E7603, &h27D071CC, &h6A3CD655, &hB83DF0A8, &h51479BAA
Data &h6B946395, &h1FA9FC16, &hADEF7EC3, &h35F917B8, &h5B2AF4D0, &h1D3788EB
Data &h1A538997, &hB49F419D, &h2AF493A5, &hA00AFA71, &hAB52CEE6, &hECE8F42F
Data &h789BEA18, &h5535F058, &h789509F5, &h180C8B49, &h6C8D0F3B, &h48E61429
Data &h6D773980, &h7ED79C30, &h72045619, &h53528643, &hB4CB7291, &hDC6027C0
Data &hDA0BFC2C, &hAD52662C, &h17E59DC7, &h11E10AB7, &hE66B8D76, &h69954AE3
Data &h83C921C4, &hDE8823AA, &h0CA8B63B, &hF9EFBFAD, &h3589C26B, &h7E591788
Data &h5DE39E51, &hD8F627A7, &hA5CEF737, &hDC9D233F, &hBEB1C110, &h844D0A02
Data &hE7E97DB5, &h2A5E30C5, &hB4B79DD9, &h33944FF0, &hC75C2ABC, &hB784C2A6
Data &h8EE4F44F, &hE578837E, &hDFAD11C2, &hB8D8C0AE, &h50537BE5, &hA8A899A9
Data &hFC5621CA, &h0E8B004B, &h3DD3D418, &h566B6741, &h614D58A3, &h0E25F2F6
Data &h7DFBAB39, &h4770B28E, &h941A87F7, &h96CD2B28, &h188B069E, &h6583B3C2
Data &h4417D193, &h93EE3A91, &hDA04EC2F, &h4FA30B3E, &h4F799ADF, &hF6F08729
Data &hC9B014AE, &h6AF079A3, &hD4EE06D0, &h0A15649F, &hE1961DF6, &h48B8B3C5
Data &hCA63C541, &h5BE163A4, &h79C1404A, &hF0326B16, &h4FA4E595, &hF4E4F809
Data &h3190A42E, &h5A3B9F23, &h1871269A, &h48DBE997, &h42E8AF73, &hB54B17BB
Data &h26F58AEA, &h2BA6DC69, &h904CB087, &h9D9DE92D, &h3C5250F1, &h871D3FCB
Data &hA08DB002, &h66D225FA, &hF4C24388, &hFA88256F, &h0A51D956, &h46782421
Data &h01783992, &h85F2F8EE, &h62CFAC59, &hA7AA085A, &h58B976E1, &h3E45BCC6
Data &h4F3FDD3D, &hF74098E3, &h19ED4EBC, &hA27D2C9D, &hB3425063, &h5F512432
Data &hC3519F88, &h51D3B7BE, &h4A485E60, &h0804876D, &h6321FF1B, &h5519D2A4
Data &h851EAFC5, &hA4679FE7, &h37A9F7C1, &hA1CEE377, &h6E5BD156, &hBB9AB811
Data &h5DED2722, &h9C6DB618, &h9C46FB22, &h9D2F4F51, &h22EE2968, &hCC55F343
Data &h4B5EDC6C, &hB710DC95, &h5C61EDC1, &hAFFE76FE, &h5574A3F1, &hDA4D15A5
Data &hE94C6661, &hB51EB8C9, &hDC916AD3, &hF68628B0, &hEF266CA0, &h5F033946
Data &h277AE5C0, &h691F39B8, &h414E27EB, &h7C9FB091, &h82718678, &h283E3A60
Data &h4E0260D9, &hECA1EAF6, &h301F0948, &hCA2FEE8A, &hB889A47D, &hAE59B6DD
Data &h0E27F349, &h192519D8, &h724CA12F, &h97D4398C, &hE2C3E970, &hEF1DFBD3
Data &hB1E8D0E9, &hCB006CA7, &h24400C83, &h863DD76F, &hE89B99E6, &h0B014CBB
Data &h3F1F6F08, &hB05E3AB4, &h22255DEB, &h0523EC71, &h062C4D03, &h19A91658
Data &h0743C0A8, &hB256749E, &h635CF2E9, &h05095FF1, &hE889B8F7, &h5AC25221
Data &hB536FC6A, &h5DA2418E, &h34296461, &h5388F5A1, &hCB6DB460, &h1D4FDC4F
Data &h9FE0B873, &h2753B5AD, &h846DF072, &hFC02E569, &hB3A98564, &hE367B471
Data &hAC48D19C, &h40A76BC9, &hCF410A5B, &h5ED99035, &h8F253303, &h96224BF3
Data &h17E0A5DB, &h33FA764D, &h02B2442B, &hECCAC77B, &h6671243E, &hEDBCF0FD
Data &h624B43F7, &hBDFD8990, &h4B97A391, &hE7B32929, &h4E948914, &h6B9844A1
Data &h5F806F4B, &hEF2CB494, &h67B80BFE, &h4D045FC8, &h80D5CE08, &hAB47AC95
Data &hF5A45276, &h748E0DCE, &h805E1A05, &h8CF6C158, &h221AE9A9, &h585EC7E7
Data &h79AA27FE, &hDDC87AE7, &h7565CD93, &h60C0A098, &h47869C91, &hF4906864
Data &h233ECAF7, &h71E94497, &h765DFCBC, &h8ED6355F, &hD1083E50, &hBF7596A0
Data &hF850ADC2, &h9B08BFBF, &hC71C77E8, &hBC23E2CB, &h294CFA2A, &h89448104
Data &h271E0CE4, &h216D07E3, &hFA1C2A11, &hAA818501, &h584D905F, &hED033D6E
Data &h1903F471, &h14B5BDC6, &h1D7101A6, &h886FA133, &h24576331, &hBA635265
Data &h7810E2F1, &hC13AB6F8, &hFED59CBC, &h49712C69, &hFDDF593F, &h92C9E511
Data &h6017A9C2, &hABE3B0FD, &hEAE8FC9A, &hB2DE9460, &hEFC9E739, &hACCDC552
Data &h208C244F, &h787076C0, &h21374D30, &h7E2ADD0D, &h396AC954, &hA0F70DDE
Data &h579F2754, &h35DB1CC4, &hC451637A, &hACA6A77B, &h8E9EEB45, &h9F17095A
Data &hEF1D1FBA, &hBEBF70AC, &hCD26070C, &h6CCCBFC1, &h6DE99546, &h341E58D9
Data &h4D02CCA9, &hD27C96C0, &h95D9144D, &h4C2AEC44, &h633BEB77, &h9A0ED190
Data &hD15A7FE2, &h4D8C10DE, &h9012BF3F, &h137A099C, &hBE598B94, &h400E59C8
Data &h61E5B42D, &h90E59FDD, &h0BC46DC5, &h092EA00D, &hDB1DFFD4, &h08978CEA
Data &h15130415, &hF02F270D, &h617D4C9B, &hF9092D5B, &hB72F18AF, &h1133604D
Data &hEEE2DC5B, &h36B38F89, &hABF9AA0C, &h9FD5E581, &hD1E4EB41, &h6BFB4C18
Data &h9C5D0201, &hCFF8A07E, &hE1895051, &hCA746482, &h40D11487, &h65CFC8E8
Data &h09466A4F, &h3D7A28F6, &h007B56DE, &hF2FFFE08, &h5629E463, &hAFD3EE7C
Data &hC80FE4C6, &h65A26537, &h9B5EBD2C, &h104E4B46, &h05611DE7, &hE8D27D17
Data &h0BFE4363, &h7D8D874B, &hE4F6C80F, &hB00F57CF, &h84AF8840, &hD0DF5DF9
Data &hBED93668, &h6D1CD8F8, &h2A63739E, &hFAFD9F87, &hD1F5C350, &hCC593098
Data &hE6562AC9, &h21149AF5, &hECAF5669, &h4DFB0BF7, &hD17A0D02, &hF7FF415B
Data &hCD435207, &h7A433E57, &h3CE1CDC8, &h8BD092CC, &h371BE996, &h71CEDE5A
Data &h89FB41BC, &h75B42250, &h9BE62D13, &hE53CC7C8, &h60310540, &h1ABF6085
Data &h2F5C2197, &h2B81888E, &hF742CF9B, &h95F1AA2B, &h04132B79, &h0D162B8A
Data &h28A54DBF, &h0E2A9F53, &h4696AEEB, &h7C983DDC, &h50A5B8CA, &h103DA882
Data &hE40C269E, &h1D096EE3, &hBA8CF94B, &h39EC0AC6, &h759E1965, &h187BBF4C
Data &h1909472E, &hBF14B5DD, &h559E1B78, &h84601380, &hDBCBCCF2, &h9743AF8E
Data &h7FD6FFD8, &h11D3473B, &h6584950B, &hE279C49C, &h013324C0, &hA908ABBE
Data &hD326FB98, &h715C3D27, &hE8D2F278, &hA0B4E7E7, &h9703B532, &hFCBB731A
Data &hE6E56ABC, &h9B700BF4, &h21091FA5, &h6E7F1F3B, &h0BB44E74, &hE3948D9A
Data &h518946B1, &h24DFF7B5, &h7F6CC3A2, &hFD6CDE55, &h07244285, &h18B1AFDC
Data &h5837EABD, &hE8699310, &hC8BA36FD, &h2742C80F, &h3D74EAD2, &h299EC453
Data &h690F5384, &h816F2972, &h3B888126, &hBB9AF13E, &h241A470B, &hF80A0C87
Data &h37B6F86A, &h86338009, &h42DB8765, &h5D3500E4, &hC088A579, &hF0EEA37E
Data &hB0F1E2B4, &h1183B7D1, &hEB217975, &hAD3E3E31, &h2BAB2AD4, &hCE28C906
Data &h6F7E2F03, &hE8E4CB02, &h07182432, &h277AFE15, &hD79C091A, &hFACACEA1
Data &h358A42ED, &hDF8A5DC1, &h59A06515, &h5BF4618A, &h8AC80DDC, &hEEC64988
Data &h38B49B80, &hE1787E9C, &h51132EB3, &hA7661CAF, &hDFCA8E5F, &h3A66F257
Data &hC8B6F42F, &h1F065998, &h8458B600, &hA1D00837, &hFF892DAD, &h9E5A2FA0
Data &h3BCF39C4, &hFAE69D1B, &h3AD4058F, &h276D8B8C, &hCA1B7502, &hD1F1BBCA
Data &h49D1EA76, &h6F0059A5, &h07FD24AB, &h3FB347D4, &h99B5E571, &h100F0E0B
Data &hE7561B28, &h7CB9D6C6, &hAA186DDC, &h6827C908, &h22B20F6E, &h71D6134F
Data &hDBC357FB, &h81516565, &hA7B11400, &hC7759F10, &h2A911DB5, &hC426D3DC
Data &h9FB4E58B, &h92B30E76, &hC296B2B3, &hA5D83223, &hE886CBB4, &h42526A71
Data &h742AB14B, &h1D7DC7EB, &hB9F5833E, &h31766598, &hB5B8ADC1, &h6266AB82
Data &h5FE2464A, &h8AD34B55, &h548E51D1, &h7E364BDA, &h40F0913F, &h7752D570
Data &h78FE70D8, &hD80A4E31, &h8FEEC57E, &hCFB23331, &hCB2299C7, &h9F5C1C96
Data &h4198C48A, &hDA9BA41C, &hC5DB88C9, &hBD7D584F, &h2AFE197F, &h8D9E0FF0
Data &hED651CED, &hF37C3DB0, &h45F6958D, &h8E01B62A, &hA116D579, &h2657A7A9
Data &hEFC2A72A, &hD109238E, &hCBE9683B, &hBCD92AB1, &hDC2F6C28, &hE6E4AEDF
Data &h237FCB30, &hB1609F49, &hA04435D2, &h6C2FBBB7, &h627E1BAB, &hE663C8E3
Data &hEB38B8EC, &h1FF49F42, &hAB282146, &h2D2EB4C8, &h48D25795, &hE4ADBA11
Data &h3935702F, &h49BE6372, &hC5B75FB5, &h33CFE4ED, &hE35144FC, &h18ED8485
Data &h1FF6C836, &hC4398A9E, &hC468B834, &h617E592A, &hECE7379B, &h19172F87
Data &h4CCA82F6, &h23BBE8E9, &h467518D0, &hAFE1FA21, &h9207783C, &hE2793619
Data &h5FCE165C, &h4F85A070, &h1A7886DE, &h25E41EF3, &h6F1A572E, &h5C3CC761
Data &hA3196C32, &h8E63657B, &h5E723CBD, &hECC65441, &h36146C17, &h6E3DE69D
Data &h9157DAB7, &hFD91405F, &hC87D529D, &hD385D89F, &h8DC464DF, &h73AFC32E
Data &hDB2DCBA3, &hB00613D2, &h3B8A39B3, &hF2959C8E, &h9CD08631, &h91444CB3
Data &hD6B33A90, &hFF3F346C, &hFA0D8A6A, &h82EB046C, &h51546AF7, &h2390CBDB
Data &hD4F06A07, &h05BEC26C, &h347D77B2, &h54FA05C1, &h8042D22D, &hF9BE333B
Data &hBEE937F2, &h324A4BC6, &h6E19B560, &h9B687796, &h849EB1EA, &h9202C94C
Data &h7BAC71CE, &hF5ACFD83, &hD4FA843E, &hCBD2D5FD, &h37544A28, &h0ACF4D92
Data &hB85C0848, &hB2B6791D, &h645EEBE4, &hA3B7D1A1, &h406699E0, &h13A4EAC5
Data &h460A6A6E, &h726CC26B, &hA5E7516F, &hCDD2F744, &h0FEFD8EA, &h1FD4A686
Data &h57601C7D, &hF1FBC725, &hE0641B93, &hE3052061, &hDDB0141F, &hE8D0FBEF
Data &hC41B23EE, &hFAD37521, &hD22F162F, &hD08B233B, &hE8961121, &h1496C194
Data &h4B3E325D, &h8A8B6797, &hEEEFE01F, &hD296AB9E, &hEF96D0C2, &hFB7E77AA
Data &h994064FD, &h745F5F0E, &h1AE23246, &h3564710A, &hB1CF9D66, &hED57F91F
Data &h62132B87, &h77FACEA4, &hA0CE1DF0, &h5EB7C2CF, &hD91E7084, &h38BBAED0
Data &hD5D32453, &h36664046, &h228DF20F, &h528D147E, &hC1A6FAF4, &h9C240FBA
Data &h7B08040B, &h699A0523, &h3382A412, &h4E3AF289, &h05D3CB81, &h13CD003A
Data &h43783389, &h9F1CE37B, &h46A52B7B, &h6F42DFB3, &h84DE01D5, &hD537E0D3
Data &h8BC4B10B, &hCA949BB8, &h88267CFE, &hB6309FBA, &h3D6DA72F, &h225EC87C
Data &h44CA7EA9, &h6F8BA6B4, &hC9802140, &h98096008, &hA793103E, &h8153714C
Data &hA680F546, &h545A144F, &h21445974, &hFDBBF646, &h103155AF, &h7A20E225
Data &hC81180BD, &h92699F1F, &hBE4E2A48, &h935B14FE, &h289E9014, &h6B847FE1
Data &hC4CDFA53, &h40017D4F, &hCCACD95E, &hDDFBCE2C, &h2153571D, &h4D786F7B
Data &hF9CB0EFF, &hCA70797E, &h19BAB017, &hB659C048, &h77F93FD2, &hFDA1B0ED
Data &h693F882E, &h37FBD435, &h3C4E3514, &hA3CBDCCF, &hEC2CE408, &h69F32832
Data &hA66AFD75, &hED548F3D, &h2405B80A, &h9289D071, &hDF9EA912, &hEB109182
Data &hD0597168, &h26B7054C, &hC5E0039A, &h65A2715E, &h26FB491D, &hF93A0C60
Data &hA3586C73, &hCDDE1101, &h627A9AA7, &h667B85FD, &hE98022A3, &hED4FE197
Data &hC94253F3, &hFA4D5C4B, &h8BE26293, &h99A45765, &h3A57BDA2, &hB353E93A
Data &h7A08A273, &h9632BB5A, &hF4A6F18F, &h447FF964, &h4E25912C, &hA6809C54
Data &hBB1F7F3D, &h229F536E, &hFDB08F65, &hA3917F1B, &h9FC0CE25, &hC47E1EFB
Data &h049F43CE, &hCC38F285, &h9055B031, &hFFC11D59, &h20EBA9F1, &hB0017F05
Data &h12C8AAC1, &h4D11A72A, &h0151D2F7, &hB0370B63, &h99CC776A, &h815D3C9E
Data &hFD172669, &hEA873E48, &h122A9137, &h74E600CB, &h373C1E2F, &hD52501DD
Data &hC731383B, &h53549339, &h9BF67F9C, &hFBD0F984, &h8867DC7E, &h31159F6A
Data &h21DF9439, &h93E64BB8, &h20B2C475, &hE43939DF, &hE91D6971, &hEBCEE4FD
Data &h23799FCA, &hA6E1EEFD, &h5442A89A, &hF149AF7A, &h74C05047, &h2656F0D8
Data &h5857414E, &h25CC1969, &h2BF13284, &h65870ECA, &h880A702D, &h0F7F7819
Data &h53EB9F12, &hBFA72321, &hB1F6EDAF, &h55FC928C, &h65F5973B, &hEF43FDF5
Data &h173BA58E, &h439B87D2, &hA4109616, &h9FEB45E6, &h9C07EFF5, &hFACB2E1A
Data &h49B705F1, &h4C12CD9E, &h13C805B8, &hE1DDEF2C, &h8A5F2401, &h3E5D5E11
Data &h84D5C311, &hE8878EED, &hC339A9FF, &h3A591F04, &h10A68C8A, &h1E680DDE
Data &hCCDC793F, &hF7343998, &hBD487CF9, &h45F00112, &h1CAF1993, &h50D2E84C
Data &h2F4E6FE4, &h541DDBEC, &h5EEADEE5, &hFDB11C02, &h4562ED84, &h34BA6251
Data &h2989C542, &h53772AEF, &hCDB557FC, &h3E8D555B, &hA3EC4168, &h0F5628B1
Data &hCD8EBC33, &h84038582, &h49596B56, &h5DF30650, &h1BF4FDA2, &h581DDBE6
Data &hEEA366B7, &h15B9AAF8, &hB140C4CA, &h97079277, &h8D58DDC8, &h064F6932
Data &hE7168267, &h91CB74F4, &hAF485BE1, &h5E38F6FD, &hF95FE811, &hCDE550D7
Data &h16AD33D6, &h3AE84F03, &h6082164C, &h8A5EBD3B, &h45CAE88B, &h5282BBEF
Data &hAA6ADD3F, &hEC98154A, &hC0877D9A, &hEBE22682, &h61420669, &hDDFF4500
Data &h0370E85C, &h8DFC18B3, &h7E4A5F56, &hE7151133, &h094F9EF6, &h336CA529
Data &h5B6F46C1, &h2CC6406A, &hD6DD1AE8, &hF4FE4CBB, &h738637BC, &h6658EE0D
Data &h62FC4EA8, &h50D07A80, &hA44DD355, &hF133AD1A, &h09748E51, &h6B1CB82E
Data &h3850F087, &hAF658E6F, &hC637A6A6, &h3B651471, &h9360F8CB, &h070FFDD1
Data &hEFED5D3D, &hBA4A0BE6, &h5975F2B9, &hA7A0DDBD, &hB7F8D9C4, &h1F8E4D58
Data &h9E95D8CB, &h2B351C6F, &hD3DA891C, &h132C7075, &h2C9ADDAE, &hA50954DF
Data &hBCB07DD5, &h12AAE05B, &h81F292D2, &h9D76B295, &h959C90C0, &hC44784F4
Data &h8F5CE106, &h3C2965AD, &hB7F2096A, &h8972FE37, &hBFE74643, &hBD75F822
Data &hB3272AA1, &hC27D7436, &h99FBFE59, &h694B0A2B, &hD75550C8, &h8DBD893D
Data &hA7E0382D, &h116A2CEE, &h070DEFD0, &hE05FEF74, &hC7C3DC3D, &h4FC1E193
Data &h52F79FDE, &h6D343666, &hA9D30310, &h84930F96, &h5B6F2D6F, &h9CE21931
Data &hC69F2D92, &h10D50A6F, &hADC61F15, &h246825AD, &h59A9D699, &h2B59802A
Data &h896149F3, &hDAE6B2F6, &h8E8A1250, &h929B2D4A, &h096BED5F, &hCD4CD4F7
Data &h8511739F, &hA0A260A5, &h85946885, &hA6D76F56, &h7768E33A, &h401448D7
Data &h8CB84358, &h80C5267C, &h1F15FD5F, &h69B893B9, &hA817B753, &h7729E773
Data &h155E8F70, &h9F387D80, &h463A77A1, &h5CD3356E, &h0D9BEB45, &hE98E7ABD
Data &hD287F0EB, &hF19A092C, &hAAF0E87A, &hAFF8CFD3, &h0305E217, &h7C5102EB
Data &h2FB64C47, &hF14A68B3, &h32BFDE83, &h7B1F5A37, &h1B77A322, &h25266DF4
Data &h145A9323, &h945EC297, &h8DE5706D, &hBEEB9AB7, &h953345F5, &h371206B8
Data &h61DABA84, &h65A96202, &h0C4B71CC, &hBCC6424C, &h92ABB17F, &h883F6ABB
Data &hF2CA53F1, &h7DE5975C, &h7CD75E40, &h7959C793, &h521F36EC, &hC9FF029E
Data &h5DEBBD3F, &h28915755, &h6F3C9458, &hB689092B, &hC84ADEBB, &h7B71B257
Data &h3A2E2E47, &h63DCD39C, &hF0C95800, &h13EA78F8, &hAE39B822, &h2FF9AB4E
Data &hD26C4F96, &h41043C3A, &h69800DBE, &h55906E40, &h24742FFE, &h7BEF255A
Data &hE9DD3CA7, &hAAD0CD6F, &h38EA42DF, &h5FA863B6, &hD749BE11, &hAA534FFB
Data &h332D87EE, &h2F13FCA8, &h2FEF62DA, &hB83D20E5, &hAAB11372, &hC781A17C
Data &hEF23D949, &h12E925F2, &h00384582, &hC16D06AB, &h4E575657, &hDB136C45
Data &hB6CD11EE, &hD7E24EF3, &h6072A7C6, &h144573D1, &hB2D0B080, &h67C36BE5
Data &h00DA003B, &hCDA14EE7, &hFFFEDA2F, &h47F01D9C, &h2AAC41FA, &hD0C6260C
Data &h81B04072, &h6F4C1E02, &h453B0CF2, &h6AEB811D, &hD750DA22, &h47D70CEF
Data &h8C9053D3, &h17FCDF2E, &hD46B1864, &h89D422BD, &h9E098BD5, &h68CD892F
Data &h2156306D, &h42F7B527, &hE0C229EA, &hBE5F0B71, &hA2D9F06E, &h0C274886
Data &h9ACC4F4A, &hC581539C, &h653B5109, &hA15718A9, &hEB64D36D, &h1D35AC86
Data &h1C94A795, &h930FFECF, &hE2EE3D5D, &hE05042F0, &h8B8C79DF, &h37E82CC5
Data &hFC2A9198, &hE50B8C1F, &h66381655, &h48A8E0B8, &hF815374E, &h6947E131
Data &hB8EBCE74, &hFE503642, &hEFCC86FC, &h6A382121, &hEA52E0FA, &hB7F4B2D9
Data &hE3019A3D, &h6EE1BD32, &h80E571A7, &h5AF5DCD4, &hB89BEA08, &hFA6F7F4F
Data &hF458F36C, &h5CEC953E, &hEAC44028, &hDDEBEF38, &h41502FA8, &h9E681799
Data &h6F9BD304, &h80126FCD, &h51F4E953, &hF414E7EF, &h930E92AA, &h33C95882
Data &hC8D82165, &h5E628AB0, &hE5D35497, &h9E4E11A1, &h8ED7D060, &h0932C121
Data &h78A9C454, &h64BE8E37, &h08EBAD4C, &h31385718, &hA0056B13, &h4FBA06D7
Data &hAF08D669, &h314F6AE3, &hEBC5C74A, &hA89FC6A6, &h14DA10B2, &h2AF583FC
Data &hF6F4B720, &hD9CC73A0, &h7A3FA6DD, &h5357910B, &h5F192729, &h76A9A311
Data &h7DFD07C4, &hDBD79B7D, &h3D6A2CEA, &h423338CB, &h9DE46008, &h8D043BCD
Data &hFDFBF479, &h97C8A11C, &hD3E01CFD, &h346E5E62, &hE5963BC9, &hA7CE8CF7
Data &h1100A77F, &hCBDFB79C, &h18C50F0A, &hDBB16853, &hB55CBB38, &hC227BE87
Data &hBEC80768, &hCFAAC393, &h7E203815, &hF7EFC0A1, &h39E02568, &hD51074FF
Data &h652CCA73, &hFA7D7098, &h06186C64, &hAAEFFE0F, &h4945B3FA, &h8990EBCD
Data &h240402E6, &hEE55610B, &hD6228000, &h73B52620, &h3F3588A3, &hBFD94DD0
Data &hFDB08BD9, &h76DB3F7E, &hFC848CE7, &hAF920133, &h04384C86, &hF734A9EA
Data &h2ACEE515, &hDF0E8F7F, &h00D7E011, &h90E5CC7D, &hEA6B269F, &h0A791850
Data &h33388990, &h75454FB8, &hD5982390, &hC1948E71, &h928742DA, &hAB1AC68C
Data &hDBAABA1A, &h4E030C84, &h56BFE8D5, &h3F27E3D3, &h0E00F4A4, &h97D98749
Data &h947736C4, &hFD51ECD1, &h77C5AE0D, &hBE0585D1, &hBEC0FEFE, &hEAA75993
Data &h84E693A0, &h3758FFCF, &hB99C6571, &h8FC5C171, &h7C2FEB93, &hD5819FD2
Data &h06B80FDE, &h5DBA0190, &h1EF3BEEB, &h06A211DD, &h1A642E4A, &h8C742800
Data &hB3D38498, &hFF743005, &h2D6DDD00, &hCBE6A94C, &h3313131D, &h1D9C0EA6
Data &h894489E6, &h8096D39E, &hD35A0EE9, &hA60D6D17, &hDC6CBED0, &hCD8B3F6C
Data &hDDA4096A, &h62DDB66D, &h3B34E2F5, &h855A0976, &h969E069C, &h1405E56F
Data &h24B0FCCD, &hF0039BAE, &h4F0E69F8, &h68C213F3, &h597C70F9, &h8D683C8B
Data &h585E5A2C, &h8210A54B, &h30406F52, &h7F220155, &hC18B26D1, &h627636A5
Data &h9F60D59F, &h01B8D520, &h1B81E625, &h16B0E4F5, &h7EFC9C13, &hBD9B0663
Data &h25404B11, &h768E5111, &hD068620E, &h30FE0E5B, &h9B58E83E, &h87BB18FB
Data &h266B6239, &h591B8B0B, &h4BE2A3E8, &h80EF18C9, &h05C552EA, &hEAD045C2
Data &h6C3C1FD1, &h3423AF76, &h1A569240, &h2EF54A46, &hA77EA340, &h6F08410A
Data &h28FA0853, &h7AE592EB, &hDAC185D7, &h46FE0D9E, &hED297756, &h1CFD4F27
Data &h373C014A, &hD50FED4E, &h60294903, &hB319DEB6, &h0C27A294, &h31DE669F
Data &h80607FD0, &h9D245607, &h3E085838, &hEC79C583, &h4FE3CBF8, &hA0506421
Data &hDAAD9081, &h795B7965, &hD3532D5F, &hA5E09F9E, &hABD5CC0F, &h4F69B5E4
Data &h500AC86F, &h6F14429D, &h4C405182, &hD22C93DD, &hAD6B05F6, &h13AC64A1
Data &hA27AE616, &h84217FFD, &h0DAB5E48, &h82C4EC88, &hC94A8824, &h17B5C2DE
Data &h58C8E2F4, &h60556478, &hEA9D7700, &h259D3B05, &h936238B8, &hD7091772
Data &h847C412C, &h461D7BC8, &hE9D58F3C, &h3BC3F91D, &h13A051EB, &h4FABA7C4
Data &h4AB1D3AA, &h177813AD, &h48EA63F8, &h144587A5, &hE85B504A, &hA82E2BDB
Data &h07E6E09D, &h61C12866, &h13E07B6E, &hC7F7201C, &hBBAE8205, &hEA7C6045
Data &h86D205E6, &h8D5A30F5, &h385D9332, &h7D9B0D88, &h37FC460B, &hE3F65DEF
Data &h9E59CBFA, &hD1A5EC60, &h3163C84B, &hF38EE204, &hC863F143, &hA1B81F1C
Data &h2B5A7025, &h59922697, &h03FDC64F, &h9C1410B9, &hF90D7D5E, &h2E544FC6
Data &h19D512DF, &hD74F0DC4, &h5BBF4605, &hC4458597, &h746BF4C9, &h10590A6C
Data &h5F2642A2, &h25813527, &h9794D42F, &h0C40D22D, &h2B9882E6, &hF5E7A49C
Data &hD35C91D1, &h7FD536CE, &h6A275C5D, &hA3CA6C3E, &hF853004A, &h59E5B7C1
Data &hE01B30B3, &hCD0F90BF, &h44B1E2BF, &h822ADD3B, &h9A476B37, &h9B24A63D
Data &h50590757, &hEC2F5C8C, &h88E4484C, &h077D1A60, &h6DED08F4, &h12DB04AE
Data &hD9F0C9ED, &hBE71F2F8, &hCEA950F1, &hA3BD8664, &h1244ED81, &hC1C1BB66
Data &h41E77905, &h85E4FC27, &h4B8658A2, &h40763110, &h0123113D, &h252AF703
Data &h1BD7B4F5, &h81FAF53A, &h39CFD43B, &h2C8CB5BF, &h9C0F6777, &hF2A1DD93
Data &h1820804E, &h8679B9B9, &h8B141B59, &h27760AF4, &hA5A4C491, &h6DD5BF2B
Data &h15C527E5, &h4A3A8493, &h544061A3, &h3C413F83, &hC6CD6D68, &h5468E842
Data &hA37982A3, &h8169EF0A, &hAFFFC951, &h6D08FECD, &h83580952, &h64B004B0
Data &hACADEA16, &hA650FFC3, &h3D8D8DB8, &h350DB296, &h230360E0, &h341B0A06
Data &h63439C9F, &h4AB8FACC, &h5BFD98C4, &hE8080420, &h18CB6E37, &h184EE9FC
Data &hB1771282, &h727D019D, &h7B2B76EC, &hE0E144C6, &hD0E7B82D, &hC75F3F6A
Data &hB519AFCE, &hF4907022, &hB0BB7319, &h6AC8AB8A, &h21BDC01B, &h7DEF23F0
Data &h246DB4E1, &h2ADAC1A8, &hEBAF1D68, &hC7D0AE21, &hADC47C7D, &h3CF3D669
Data &h77A78D6D, &h91622218, &h5537B33D, &hBBC3EF2A, &h8BFAD390, &h2D55994C
Data &hA20AC4A4, &hCB7FED6E, &hB80335DB, &h66EE2C6B, &h4B99AAED, &hE644B18E
Data &h7A218FEA, &h4CF443AE, &hDA4BEBFC, &h953C2E05, &h0CF092CC, &hABE6C141
Data &h20355279, &hFF386515, &h110449BA, &h6380D6CF, &h2C91950A, &h97897D37
Data &hAC3216AD, &h8F4BC3A8, &hEDCC1EA3, &h33A37E03, &h15C93DA6, &h6EA5200B
Data &h1E98C77D, &h396A7471, &h6039CE15, &h89A83374, &h2944697A, &hF62AA5DA
Data &hCF499048, &h70ACA588, &hECCD5749, &hA1CBABA0, &h8DB1AAF5, &hF39A9686
Data &hAE2A81B6, &h819EA670, &hD67B1722, &hABB2BB87, &h6E9AD996, &h843CE763
Data &h2A53FBAD, &h48F2AD1C, &h3EDD3BE6, &h735DD436, &h2D2DEA02, &h29989661
Data &hA6439E7A, &h569590DE, &hD7DABD65, &hDFFFC154, &h32A42994, &hA0F2E4BF
Data &hAE33505F, &hC7452F5D, &h12131E73, &hBFBF5B6F, &h29745304, &hCFDCE5A8
Data &h60EA2D5B, &h088D86E5, &h83FF297F, &h98043A3C, &h32CADBEC, &h3750274A
Data &hF8133865, &hD3939386, &hE6D1323E, &hE563AADE, &h62C39001, &h4B51B624
Data &h56E59600, &hE45C297A, &hACA1BA88, &hC33F6544, &h46D0AD37, &h5F0978D6
Data &h535D80A8, &hB63CDD2B, &h62CEAA89, &h3286D42F, &hF1284320, &hF8077D9E
Data &hC0841432, &h4407C39B, &hDD9A9A13, &h53B64B10, &h78899E6B, &h82B2D861
Data &hC23ABFBA, &h61D74D4E, &h39E18AC7, &h49A0B9FE, &hC499755B, &hFF90C2B7
Data &hB7737247, &hD4E2E915, &hDF86AB23, &hED0C3BB9, &hD096C7C6, &hC8BAEA85
Data &hAE60EC4F, &h93652FBB, &h5D69A808, &hC1441C17, &h7974104D, &h4C4A8B83
Data &hD214D607, &h03744B02, &h00FD1CF5, &h59C63B37, &hC06D9C3A, &hE4844E28
Data &h96C19E10, &hC5914B00, &h228E8111, &hBAC1BE6D, &h358CBF7E, &h99883087
Data &h64B6CA13, &h501EECCF, &h8D33454B, &h524DEAAC, &hAC45CE2D, &h2416F79E
Data &h7E714D50, &h891E7066, &h77462E8D, &hF6FF5C7A, &h64FEAE4A, &h0FD21FC0
Data &hAB8A01D8, &h1A81BFC6, &hB7CB4C2B, &hB8DB6577, &hAD867577, &h8A03FD39
Data &h36D74019, &h1DE2B43F, &h773B36C8, &h9A821C55, &h8C19A96B, &h18BEC106
Data &hA238FD7C, &h268CDCEB, &h5DB45B78, &h2E2A8BC3, &hD06C165C, &hD17E8768
Data &h54E4FD34, &hDC1AA99E, &h7A94B846, &h45B18D2C, &h357373EC, &hD4D010E4
Data &h69BBB70B, &h6A3211D5, &hEF133B47, &h92B7D142, &hD6883268, &hEC038F60
Data &h5C3EE806, &h514B7618, &hA2AB325D, &h53B8935B, &h8C2491E7, &h5245C052
Data &hEE77787D, &hBE6DF31F, &h4774E68F, &hC78DD34E, &h8B18658C, &h6E77CFB6
Data &hB4D6667F, &h60F2E05C, &h5D3E301E, &hB60BB8CC, &h846C67E5, &h092F87E0
Data &hC10DA020, &h5A2CC1D2, &hC3BC93BE, &h9BFB7A05, &hBF00702E, &h38686EB9
Data &h19703021, &h5241A81E, &h888F363A, &hCA7169BD, &hE582BBA5, &hD9892EC3
Data &hC7979BD9, &h36CB4333, &h07623393, &h4625C318, &h25E5B034, &hADB617F2
Data &hBDE878F9, &hB0205F4A, &hC9B8BF3A, &h17206356, &h59E62402, &h64A27BD1
Data &h02302047, &h170D8304, &hAD338684, &hA2DF2CF9, &hD18102BD, &h9B7FFB95
Data &h8ED0B392, &h86E61AA0, &hE02B2013, &h822883C5, &hA5BB5519, &h009FE06C
Data &hD2357776, &h6C04A1EB, &hCA0766F8, &h98398DA5, &h0CBD69EB, &h3CC94502
Data &h12827AE0, &hC4FD28E4, &h22743D7E, &h89BA4134, &h9D15D6FD, &h87D7F510
Data &h00FC3F53, &hF60F6391, &h92D73A33, &hA4C2A853, &h12303C75, &h7B1CEC5C
Data &hA7E6B01C, &h9A2A24EE, &h2F8E8490, &hF095DF9F, &h0D413C69, &h3DF8A4A6
Data &hC9D55B70, &hFED5103C, &h65382B6C, &h3A47F41C, &h9F6F2C3F, &hBD53F868
Data &h83E617B4, &h2842F95B, &h9D5809D5, &h446697A2, &h7F394773, &hA4A6D8D4
Data &h848F3D68, &hE3D4EE1D, &h005A87C1, &hBE665055, &hCB7A7D7A, &h59AC8E3B
Data &hB47677BD, &hDAF5B17B, &h11C5C2B3, &hB363F3B0, &hFD40263C, &h9D945B4E
Data &hB70F68CF, &hA483466D, &hBA48825A, &h626EC9C8, &hA6AF55A7, &h38A6DEE6
Data &h762E642D, &hAE030283, &hFED99212, &hE06CBF05, &h5204C160, &h2488E146
Data &h116604F2, &hDDF59147, &h58968772, &hA8572A63, &hFE6D26DF, &h2148708C
Data &h96473F71, &h5369AD42, &hEF32E25D, &h15ED8B95, &h19273BC2, &hB01CA754
Data &hB61593D2, &h1F1DC6F1, &hD34428E5, &h315274B0, &h12E2AA98, &h7F1DB2B8
Data &h4C3C8429, &h3A183D14, &hCAAF783D, &h2894689F, &h24EB9281, &h3EDFE706
Data &h88F851B5, &hB8215430, &h2605CCC6, &h7F3A4190, &h4B461A49, &h5298CB31
Data &h13A558C5, &h2C01374C, &h3595402C, &h0E4DDC73, &h0FB5F52E, &hA8C345BB
Data &hF7DCF77C, &h8C903224, &h5ECCA5F0, &h51455B95, &h9CF27900, &hF8BF1D49
Data &h2720BA4A, &h615A04A4, &h5F8C0F8D, &h6A40BB76, &h42736FD6, &h7452A0B3
Data &hF01F573F, &h5E66BB28, &h256DAC06, &h7CD77EBF, &h664AF882, &h8B7E0C11
Data &h60B5A6DE, &h53F157BD, &hB26160F4, &h951FEC58, &hF1623F4C, &h57A016DC
Data &h7A0D9AF6, &h6332451F, &hA1F31826, &hDDD5BEB9, &h7BFE0D57, &h57C84400
Data &h7110EBD2, &h4A2BB96A, &hD9617031, &h17E3E875, &hD4B21123, &h582D91B1
Data &h8053D87A, &h2A435B03, &h6898BBFB, &h7E744918, &h968E5878, &hFB6FE630
Data &h3553C729, &h99BBDA44, &h26B5A97A, &h5464F153, &h04CDB9FE, &h8567039D
Data &h6360AD00, &hC9D5CE38, &hB6FE15CE, &hD5B98FAC, &hA1A32B85, &hEDF777BB
Data &hAB962551, &hEBF98AC2, &hA99D3926, &h4B6ABAB3, &hA8246A4A, &h2D924327
Data &h5A509991, &h8EC2C966, &h06AE39ED, &h82F29204, &hB1BFFCF9, &hE0041EED
Data &h93167994, &hFDA65163, &hD7D1975B, &h9A064000, &hC22505F5, &hE61FF857
Data &hA734FED1, &h904824A7, &h92DE35C3, &hACE6A39A, &hE75EBCA6, &h1A7CCCD6
Data &h18AF6255, &h9C0CB332, &hC02113AB, &h0556B708, &hCB337A9D, &h8E16872E
Data &h7FED2943, &h3C631AEC, &hD54AF158, &h357CC0F9, &hC5646909, &hDD78A3B1
Data &hF30C4C06, &h3830C27E, &hC032FDA4, &h5FDF6AC7, &h91A985FB, &h8397A2D9
Data &h2B1A4B67, &h89ED44A5, &h38858555, &hCDA9E806, &hAE4A6833, &h48528274
Data &hFD80C47C, &hC50A0B64, &h7EB0BB50, &h0C4ED95C, &h4EB62CB9, &h83958694
Data &hB20E2D7B, &h992A8654, &hC8F8A526, &h6A39342E, &hA3FF8759, &h82CCA054
Data &h7B56A5D8, &h35967E0C, &hD136557F, &h93E98CB2, &hD925D63A, &h9E5463A4
Data &hA85E8070, &h00D681A9, &h8E42D30F, &hA0DA7B1D, &hFE034F2B, &h75320FE4
Data &h5AC781DC, &hFC1124A2, &h99C22E47, &h314424E1, &h61AD03F5, &h515988E9
Data &h25EC3D36, &h55440477, &h230994B4, &hD7A38FF7, &h7569E541, &hF7FE0287
Data &h9497947D, &h6FF4AA47, &h725222F4, &hAF15CB53, &hF866BA06, &h99C56274
Data &hF1165EDD, &h01656770, &h317785A3, &hF6A5132A, &h8CA8B16F, &hF37BB90C
Data &h74A4DDF3, &h7162F0C6, &h5EC2C22B, &hD743575C, &h7B80B062, &h6197E601
Data &hAED0D88B, &hA9C01166, &h0A0AADA2, &h312174A8, &hB075D9D4, &h8E02FB6E
Data &h0B967250, &h9C8AAFC2, &hF4B468E9, &h5F11016D, &h506E8897, &h34D21AC8
Data &h5AA2B8EB, &h8835508B, &hBC0C2E7B, &hE439D41E, &h95B87040, &hA1AFE3B3
Data &h2888CA21, &hF30A3BDE, &h6DF1A0D2, &h23FDF98A, &hA103DD89, &h90624623
Data &hFA55ED36, &hF1BC7014, &h9B083E77, &h90139E74, &hA6DCBADC, &h16F173A5
Data &hBDAE1945, &h22908210, &h57EAED83, &h27F8672C, &h4509E818, &h7F50A28F
Data &h921DB9C1, &hE829F295, &h70747792, &hCF588490, &h5569D68F, &h4BA2A3C5
Data &hA3102DA0, &h63BB5357, &h92AA9C13, &hCB8BCD2D, &h1977F0A9, &h277E62C7
Data &hCBE7C446, &h3DE03CCF, &h966D21DD, &h202EEDDB, &hADAA3BB1, &hB33BB997
Data &hB0098CF6, &h10C46B98, &h2E18261E, &h4E482E74, &hE78FF3D4, &h20436CC0
Data &hC19FFE48, &h12457F7F, &h62FC9B73, &hF05B9F95, &h2CCBA99F, &hF2BE9E95
Data &hE54393E1, &h0E9812A3, &hC5CD2F65, &hB695A990, &h9D38CF63, &h0C8A0E7B
Data &h22BA8C8F, &h02732989, &hD749CF4C, &h3FE633EE, &h47188EE1, &h05A5FCC6
Data &h541D8C79, &hFF1E358C, &hD22D1FBE, &hDF21984F, &h914E4429, &h3DDBF0BC
Data &hC4DEC832, &h9CAF6A84, &h91D7D238, &h99E5C3F9, &h7BCE998A, &hB7950575
Data &hAA71C8C9, &h4414F6B9, &h222CBB74, &h29D2B8AB, &h613A7659, &h33BA112E
Data &hE780EA8C, &h6B26C853, &hB5BD54E6, &hC9DEFBEF, &hE33A8C3E, &h0EEF4306
Data &h92D93A20, &hBCB9CCD5, &h19A52425, &h712D3EC6, &h61A09BA1, &hF75023E1
Data &hC33217C2, &h8D1CF87F, &h03F3C279, &h322C2B35, &hB0B33F5A, &hD1B281CD
Data &hB99066AE, &h143BA3E2, &h16280313, &h4C411BE2, &hA0C8066A, &hA8DF5478
Data &h30E5975B, &h68804E2F, &hC7F2233E, &h74EF35C2, &h623A483F, &h3F4986A6
Data &hF4D01BA4, &h01084A09, &hA8E80D16, &h68B38F2F, &h3F51B726, &hA5D7718C
Data &h37EE4050, &hC4DC0A0A, &hDF82F2E1, &h6756A898, &h3D885FA5, &h58DF848E
Data &hECD1B003, &h273F7FBC, &h00016C7E, &hB3C819B2, &hC965B3AA, &hD33DBF8D
Data &h4BA144E1, &h96D61881, &hB45A1E2F, &hBF236BB1, &h352C127F, &hBD0E0212
Data &h9DF14CDB, &h7243344E, &hB5351B32, &h05873F68, &h877E70D9, &hDB498CAB
Data &hCD263A88, &hF779712E, &hB739A29A, &hD051CF26, &hB86A02C5, &hCBE5D447
Data &hF9FD3D8A, &h59266E36, &h6CBD992B, &hBFB4F73E, &h97A2B756, &hF4153B3F
Data &hD8008573, &hD361A2A6, &hA1AD323E, &h7967F20A, &h7AFC9CEF, &h0F359D2B
Data &h23B0E6A5, &hAFA5C7CE, &hF19380EC, &hF9C42CAB, &h24938040, &h935E4A76
Data &h902651CD, &h4169F725, &h0137F931, &h5F260E6C, &h1EC0B8F6, &hE2F5788D
Data &h97339BC6, &h227DC6DD, &hF21C10D9, &h14F6ADCA, &hE7B824D5, &h61B1AE5F
Data &h20E26EED, &h9BDCD7E8, &h2F865FAD, &hA348E69E, &h9B4BB603, &h17687FF4
Data &hCEC9B6DA, &h3C732A6C, &hD9179A6D, &hF4589F97, &h3E65BEE1, &h6F1398D8
Data &h342FC5EA, &h7E5EFCBF, &hD017D5B8, &h22D8E82A, &hFCBD4A71, &h8EDBBC5C
Data &h394416FA, &hFE402ABB, &hEDB4AEBA, &h7CD186F2, &h5067824E, &h0539A2FD
Data &h2CB5CA84, &hFAAFB1A4, &h19842685, &h7DF11255, &h6C265229, &hDE41082F
Data &h4CDA6AC4, &hEA5017F6, &h7989B7DD, &hD40C9190, &hD5ECBE8A, &h36FCFA71
Data &h5DCFC020, &h4B16CB6D, &h076E7A8E, &h9BECB10F, &hBC6F651C, &h82150B77
Data &hECA20FC2, &h9E0A825A, &hBCE88127, &hEC12B182, &h8E9A3A32, &hC4596740
Data &hD35F536A, &hC6FB1640, &hC988149A, &h8E973C82, &h76ED81D4, &h41A2FE5E
Data &hDF31183E, &hDC5D6E90, &h39972DDC, &h492E9937, &hA1486EE3, &h67C58E2C
Data &hC05B9244, &h13F83500, &h03B3CF70, &hB432F247, &h58F9DD5B, &hB26C7F46
Data &h79E58742, &h47AA59A9, &hC4AB6CE3, &h776761CB, &h2B9F638E, &h70414081
Data &hD437DF70, &hBEC422D6, &hEF3069D7, &hF87803E5, &hF44E9819, &hD2A87950
Data &h897040CA, &h97C2149D, &h04BA7879, &h22DE852F, &h3FF3CC8A, &h42CE301A
Data &hA44C1567, &h57EB07AB, &hCF0919FA, &h0482C8CD, &hF7D58EFF, &h9C7810C2
Data &h8E2186B4, &h57FD81D5, &h115DB972, &h0B7D54EA, &hF569D227, &hF403CB22
Data &h5174AB0F, &hDC5C00CA, &h2198050F, &h1602A667, &hA6C0426A, &h4BFFFBD0
Data &h8619F459, &h5C414739, &h468D9EF5, &h994EEA96, &h018DC45A, &h1FB0362F
Data &hF5A10973, &hB736E304, &hAC999273, &h208D488D, &h5289C5F5, &h084EF5E6
Data &h62DDD1C7, &h8CC3F765, &hC517E7E5, &h13C48F7D, &hC7D86177, &hAC08BCB1
Data &hB0312D25, &h73258C36, &h4F9E797E, &h5E1E2C60, &h7FAF53A0, &h7CC4C13C
Data &hA92B254E, &h0A87FDD4, &h6731322F, &h4021E88D, &hFDF9FE66, &h1B0CD9E1
Data &hAB9E887B, &h5B0688C0, &hAD470904, &h16BB1208, &hA4922F8D, &h3D04CB93
Data &h8D6A0521, &h88ECAA00, &hB60C59BE, &h9FFDF51E, &h54FBAE5B, &hC4DEE646
Data &h8AA1A2BD, &h38CC0FBC, &h23CA05C9, &h72BC11C3, &h2F748C1A, &h0BB68D0E
Data &h7932FF95, &h2BCEB7D7, &h6DB35FC3, &h658C8F1A, &hC5872E45, &h04B27825
Data &h7203E86E, &h42CAE9C9, &hA2EFFC8F, &h4EB1A976, &h0DCEA4AE, &hEB7F3F5E
Data &hC40ADE78, &h76FF6D80, &hFE015F95, &hD951537D, &h3E6978E7, &h529CAC79
Data &h38341AC9, &h201BB103, &h18793329, &h5A848981, &hDF21FFDC, &h442C0910
Data &h81902D6D, &h4F869B20, &h5114038A, &hC69BD3A0, &h1C58BD3D, &h554090CA
Data &hB72D91CE, &h4AD71977, &h8D0A5A21, &h53F7C63C, &h070A24E5, &h278B56EA
Data &h47303CDC, &hEBB8A523, &hACD4F9B5, &h6DAFE700, &hE029A227, &hEF7A8931
Data &h14F0E2D1, &h3D4BA0A7, &h9CB8AC01, &h3CB25DD1, &h99ABB8C9, &hF3B79C9C
Data &h0281E1C6, &h844CF72D, &h3AB7C541, &hC36C2694, &hBA3180D0, &h0923607C
Data &h529A02AA, &h6E8E435C, &hD2E0173D, &h2D423575, &h6CA57A0A, &h6907FF36
Data &h73D5B97A, &h13AD8B80, &hE9BC0055, &h45AA71C8, &hE3CB7645, &h41032266
Data &hD992BD96, &h4819B914, &h51B7D4E7, &h773A7312, &h5C38AEAD, &hC88688B9
Data &hB7A286FD, &h9C2059C0, &h443B99B6, &h854B1136, &h0F8D8EBF, &h578F7C8B
Data &h2511A55F, &h58E636B7, &hAAE49BC3, &hC0DA8A94, &hDC28F1A8, &h6B88422E
Data &h32EEA8B2, &h3A47F683, &hCC9939CC, &h6C1EAE6C, &hC59B90E4, &h6C3DED31
Data &h390FB6BC, &hFE001EBC, &hA19BAD98, &hAB1D5C95, &hC41DE3F2, &hBCEC9B76
Data &h61ED1E8F, &h5B937079, &hC10D76D0, &hF4ADED31, &hBC3BF7D2, &hA94D94C9
Data &hBA19181F, &h83EA6E84, &hF7A4B868, &h0BB856B9, &h9ECD3AAE, &hD68B9F20
Data &hFE467361, &h3195C4B7, &h04E107AE, &hC311F48C, &hB2DC86E6, &h4A982469
Data &h1D799CF9, &h50A3B1FE, &h825D91E0, &hC44AE695, &hD47CF9F4, &hAF916753
Data &h09BA5AD1, &hCEDA4DDC, &hEF468324, &hAAA6E992, &h01B437BC, &hDEA5520F
Data &h8491A2F3, &hD9FA5CC0, &h2DC90864, &h8D8DB944, &hB484DA03, &hB8538BDE
Data &hA38B28CB, &h342E1DD1, &h4C0CF4A4, &hEE0FB47F, &hA9ACC0D3, &hCDEE4D91
Data &hED455D18, &hBEB1B17A, &h121CAF46, &hC8C62E94, &hF1254D7C, &hA9F6AABE
Data &hE0F45B04, &hFC944E7A, &h467CA439, &h52F10E61, &h0447954E, &hFFF9EAD9
Data &h87C134A5, &h3CD29290, &h4D339856, &hBCCB65BA, &h6ACB0652, &h207BD9E9
Data &h6881397E, &h5C23A6BC, &hB88DAE3C, &hBAB89F2E, &h2C40EB4C, &h20AB73FB
Data &h3A132F30, &hD201C259, &hA32C7985, &hB7ABD7F1, &hC1698676, &h4DBE90A0
Data &hFDA6F426, &h49791AD8, &hC7B64244, &h8DDE9B0D, &h884D6159, &hFCCD26FB
Data &h009CEC9B, &h07F7310F, &hD1AF0D5F, &h7EC33B22, &h7CAEB7F3, &h1F161F6A
Data &hDA093914, &h23B6D6C2, &hA4D01878, &hE9AE8308, &h577B3FE5, &h00418B0C
Data &h40D71B6C, &hBA13DFE1, &h5D5052A0, &h903F5E6E, &h8F90D435, &h4C15D052
Data &hDD0AC313, &h6609ED27, &h9422A42A, &hFB8F9B15, &hAD25016D, &h366CAB4B
Data &h81D0C99D, &h105209AB, &h13FD847E, &h8C860BB0, &h6CAE4EB6, &hC7852ACB
Data &hFC82FBD0, &h97C5CF82, &hF8A7831C, &hC1390EB6, &h470E4082, &hAF4F9A2F
Data &h2458158F, &hCD3DC8AB, &h4C839839, &h8CDDA69D, &h1117E214, &hD3B17101
Data &h5A6414C6, &hAC26282A, &hBA773407, &hCEAAF470, &hE52CD56D, &h9BD326A5
Data &h5BBBD77A, &hA12AE35D, &h7DCF4E68, &h964FB681, &hF8243202, &hEC4F0900
Data &h9547990C, &hAD6CDC24, &h51229B53, &h1829F8B3, &h15C55EF9, &hA5A1A902
Data &h30047033, &h6EFBD8DF, &h8049BFD3, &hECE8C1E8, &hD0D29CB7, &h7A194B95
Data &h7D83A38E, &hEAF50C89, &h57D2EFED, &h2EDC04F9, &hD8A8F073, &h35B326AA
Data &h78DDE10A, &h1D9445CD, &h5D5E017B, &hB18E60C9, &h3FCD2574, &hB7CC1A6D
Data &h87C0C9A8, &h0D09493D, &hD3287E6C, &h0ABB8089, &hF706730C, &h72DA96D3
Data &h6DAD8A95, &hF1854583, &hE6D6BF9A, &h9CB97662, &h94CEA575, &hE0305350
Data &h78473141, &h44345DB4, &hB28B3FC4, &h99CB6979, &hB0F974F3, &h9E40747C
Data &h2F055C11, &h84A70455, &h9EE05F55, &hD56602F6, &hEDB3A9D4, &hBED2D402
Data &hC67ED88C, &h533EA48B, &h7A8ECE44, &h90A7A49F, &hA6130B39, &h82944D9C
Data &h24B8B055, &hB8D3F267, &h7CB98BC9, &h2A8B4809, &h5BBB8F9F, &h7B70610C
Data &hF2F04EC5, &hDF1D3571, &h4D388A84, &h67612EE9, &hF0213CF2, &h9F7FA16B
Data &h24DC50D9, &hA8C5DAB7, &h4910888F, &h98EC35C6, &hA74BEAF7, &h3D5EF0FD
Data &hC5E39A7A, &h26FBA27D, &h66FE0196, &h4C419ED4, &h27BD0B17, &h88DAC2F6
Data &h653688B3, &h12367477, &h50635E90, &hB8AB7C40, &hAA1CE8F8, &h405D1143
Data &h4B2973E0, &h91702061, &h08BA3F36, &h9D94C19A, &h38B5ADC8, &hA1DEDA7B
Data &h2070BD2E, &h3BAE1772, &h029F91FD, &h6AD60CE2, &h2C9B9A47, &h36F650B1
Data &hE136C7A9, &h08EC8413, &hC1654E98, &hCB48375D, &h5326CE11, &h0DC3B6DF
Data &h47ADECC5, &h9CBB2849, &hD7977E5D, &h9CD64BA0, &h8D00E134, &hCE56D45D
Data &hFB55E3AF, &hB0BEDF63, &hE11D4317, &h993130F1, &h2BEF78BD, &h98721E5F
Data &hCF22A65B, &hF628D0EC, &h846A20C4, &h8D5D35F5, &hF1796D38, &h6E63B77B
Data &hBA1CB3B2, &h127D2D1A, &hC24DDEE7, &h73B033B1, &h8FB1D35E, &h94BBAEBB
Data &hBAEFEEDC, &hD89747E5, &h484D33A7, &h03228940, &hD720C243, &h70315618
Data &hE9D8C05D, &hF250F28A, &hD6865AE4, &hB0DB1F39, &h8CF40A4C, &h94D6CCE3
Data &h97628F05, &h28C9E51F, &h5FD10E72, &hB544EBF0, &hBD842A39, &h1881A797
Data &h5D8777E8, &hF15E0FDD, &h50545696, &h93A9F9FA, &h17141DF7, &hD004FFC7
Data &h670EA7E0, &hFF90996C, &h1CED7293, &hD46F2B7F, &hB19B7A3E, &hB2BF1F7D
Data &h83305576, &h3DA6D408, &h8D36E5B8, &h79C8981D, &h5FC2D1EA, &hDFAEAC9C
Data &hC4807117, &hB326B43A, &hF7D26014, &hF8CC6DD5, &h6A6BB9F9, &h82E203A9
Data &h77611C35, &h5EC29694, &h3BD8D2C1, &h42891AD7, &h7903FF8F, &h5286CEBF
Data &h0F4B4DF4, &h59C60C32, &hE4CFD11C, &h8FEA1FBD, &hBC887798, &h7C7B0ED6
Data &h73F189F5, &h7D2C6A30, &h7679D644, &h69271451, &h930DC961, &hE0CC8200
Data &h64A06701, &h9E2FCA0B, &h2E81AF1B, &h3C56C98C, &hA9AE7864, &hDD1B9A3F
Data &h13BCC61E, &h1CF6FB4B, &hC3FDFEA9, &h85AAC6B4, &hDD367CF5, &h2637F035
Data &h42B74CB7, &h961E0B14, &hF870EE31, &hDCA8E382, &hE660927D, &hE6CBEA0E
Data &hE2001A13, &h8A566E99, &hB89B2BC9, &hD8DAF324, &hBC349337, &h894CE39A
Data &h96BA6754, &h4F33DB8C, &hA623F187, &h742779AB, &hF86D9A41, &hE2B29E6A
Data &hA464D4B1, &h75830E7F, &h05D92179, &h5A583EB2, &h512C0A49, &h2DB3A7FD
Data &h6956FF5B, &h1AEE9AE6, &h4D7A8873, &h216306D1, &hB8B4A3AE, &h4FBEE37A
Data &h9EA6AA97, &hB20D00BC, &h174FD757, &h6177F4A6, &h7249B7D0, &hDDDEC84B
Data &hF3DC530A, &h742B083D, &h5E90D1A2, &hD343501D, &hA2861056, &h33009190
Data &h9B4CBD7D, &h191F1AB9, &hEA1863B7, &h143E2EC7, &hAA5FF30A, &h14BCA6AC
Data &hBF6D3F9F, &hB87FC78D, &h08509BC8, &h070787BF, &h3CE1BB68, &hF4C5BDF3
Data &hE087C496, &hFA43E261, &h3C095580, &h55B2436B, &hC9261E11, &hFD065AA4
Data &hDAF90556, &h435DB1BE, &hC5F97D6B, &hE6D4788D, &hC4D8A5BB, &h68477B95
Data &hF4507077, &h68C875F5, &hD467CBFB, &h76719CE3, &h473B7E47, &h3B077432
Data &hC98AFFFE, &h8908DB9D, &h719A2727, &h2E6370BE, &hBDD4CBA8, &h527935AF
Data &h5CA918B2, &h2835EA50, &h14F8E0AF, &h9925C9E6, &h94467933, &hD010DE56
Data &hD8F55359, &h2A1988B6, &h38C85E26, &hC251E7B3, &hBC30BCDF, &hB0C20718
Data &h8E2B7493, &h72E94592, &h7BA2C222, &h4C4D277E, &hF4FEA629, &hAB032B35
Data &h0B9A2F8F, &h922AA9DC, &h03487BBD, &hE217F604, &hA91CBCF9, &hE7523F7C
Data &h7EEFBFAE, &h059391F5, &hD9559D81, &hB668A837, &hE7A124EB, &hE0AE124F
Data &h8B71C0DD, &hC09595BA, &h833D3705, &hBA09F0F1, &h6D8B4547, &h4B2C15C6
Data &h56A8B972, &h39AF5509, &hDE6B88D8, &h383444C3, &h8B4CE5E8, &h8D76125B
Data &h92EE81DA, &h4A9526A5, &hE26E2931, &h6B23E6BF, &hCA5EA8D9, &h3E97788A
Data &h60555187, &h3ACCD10F, &h4023F488, &h646B8FAA, &hA1928561, &h8FF4A959
Data &h17EAF876, &hD74A0FC1, &h236C8D3B, &hDD1AC130, &h5316B131, &h07080F3C
Data &hBC256F01, &h5867E6CF, &h94CB029A, &h98CBC837, &hC2885A44, &h58AD151A
Data &h91AF5D91, &hAA602CF7, &h7624B1BB, &h573C044E, &hDB3C4C60, &hDFE806B8
Data &hBE216718, &h49987189, &hD13B31FF, &h68CD520B, &h76040485, &h7ECEFF8D
Data &h83A27AE7, &h585F9A54, &h76EFB5C4, &h50CCE1B5, &h1214F238, &h163ADBE0
Data &h899004F9, &h10B011AE, &h3560A53C, &h56DE1892, &h67B70D23, &h0FA8AA82
Data &hF3E6CBA8, &h1B2D2B3A, &h41E69798, &h7454EAD0, &hF51BE9DC, &h4EF9C0EB
Data &hAF1464E5, &hFC65F883, &h4EE4F594, &h8EA91BF8, &hB62F7097, &h72035747
Data &hC6ADD036, &h7A8753E1, &h89774A44, &hC0C4CA2B, &hB15960F4, &h58255567
Data &h9827472D, &h33B23243, &h30C21678, &hA45FF062, &hDDF8D167, &hE65CF467
Data &h80849F19, &hD2880E91, &h8BFA610F, &h0FF6290F, &h9F4C2C5A, &h3156C4C5
Data &h09F67372, &h526547D0, &hEDE4C2E1, &h762251E1, &h9728BEE7, &h9DC34223
Data &h73BFDDFF, &hA99FDF39, &hA97AA0A9, &h6FD48561, &hB5E43603, &h085162D4
Data &hDA9B56CB, &h4E74394E, &h16C41450, &hE53BAE3B, &hE1C6CD90, &h88A74D70
Data &hC29D4114, &h62FFB7DD, &hA1401B47, &h2D348E46, &h4B2B6A3A, &hAD38B1D0
Data &hE8202C6D, &hAF5AECF4, &h32F9017B, &hA75E5E55, &h0D7CEE08, &h101EACE7
Data &h8249686D, &hB0B24282, &h4F50BFEE, &h29DA10E5, &h3A770456, &hED03AD4F
Data &hC0D3B93C, &hDF1BFF75, &hCFD0557D, &h5D0AC668, &h7E7CBB02, &hFCD365FF
Data &hA3DADB7D, &hA336E22F, &h7B624E52, &h9420FFCA, &h4757F6B2, &hF374854F
Data &h15C5C77A, &h505B2BAE, &hDFFF9C1D, &h88FA99ED, &hAA40B0E5, &h25D2ABC2
Data &h93C09A4A, &hF45AFBE2, &hC4CD0CB0, &hE42DBAF9, &h2B68387A, &h2D90BBCF
Data &hD34D3FD1, &hA3ADC86A, &hB7FB69F0, &h1FD930B5, &hC351AFE7, &h91A97190
Data &h6DC7380B, &hAE2B3171, &hF3C7B912, &h7D651C76, &h154B79FB, &h26DF1FBA
Data &h34D04BAE, &hEDA80126, &hA0B4933D, &h7C9A5787, &h07D64C9F, &h664A2EB6
Data &hCF94A532, &hFF924EDC, &hD588664E, &hCD771662, &hA1691516, &h430C5968
Data &hCF41E7D0, &hE3CEB796, &h0E63BF3D, &hB437B30D, &hD99E5415, &hB576FDD1
Data &hA00DD30C, &h57A08BB7, &h5D3F015E, &h732B473C, &hD048A598, &h04A7ADF9
Data &h0B9F22C4, &h35ED0CCA, &hC22AE5D2, &h224C8EE3, &hBCD112A1, &hAC29645C
Data &h5AB72D15, &hFCA45339, &h35182526, &h9BB256E1, &hBBF4EDF2, &hC92BFCEB
Data &h04686DE5, &hEA0A1DC6, &hCB298C13, &h6B32B668, &h75CDF93F, &h8EEABB9C
Data &hE799A4F7, &h51DF2ABA, &h75B896B7, &hF06F7043, &h6C66C10F, &hEE6278A0
Data &h6961D746, &h82B334E7, &hA17A225F, &h794C3223, &hE7A936BE, &h63981F6C
Data &hCDDECCC9, &h89535DA3, &h4ED89B6B, &h03AC9D37, &h8A7F32C9, &hE3124D54
Data &h49682534, &h0BE95347, &h15501F64, &h47392F22, &h1036F743, &h2DCDBE54
Data &h458122EC, &h571D2CAB, &h91851D18, &h3BECAD34, &h11B66303, &h0F7D2670
Data &h5EC7949C, &h3B303676, &h5F65B9E4, &hE5CAAA6A, &h28A16B2E, &hD1C45E4D
Data &hD53B49FF, &h12051669, &hB8A8DCEE, &h28130B49, &hAB90DAC6, &h55528DF7
Data &h127922EC, &h340CB687, &hF9FAE9BF, &hB625400F, &h42306B93, &hFA193B7C
Data &hA5F3D59D, &h9948FF38, &h379BF8E5, &h91912DC3, &hDF13EA37, &h31F6ACAA
Data &hA152E861, &h3737C0A3, &hC2491804, &h473301FE, &h10E40B1A, &h57C44B54
Data &hFFA425E5, &h93170BB2, &h6F14FB44, &h75B53FF9, &h824B2386, &hBE903608
Data &h74E6E085, &h4A244F0B, &h9B30BE32, &h5C2AF40A, &h917E3BA7, &h7A676F1A
Data &hCFB21E39, &h74918F21, &h5A64568B, &h1F511874, &hBD2BDE22, &h870CA1EB
Data &hCAC76AAD, &h94C6B41A, &h31F6C1BC, &hDDE3470B, &hE6D036AA, &h9ACB60CD
Data &h9491DA3E, &h062A5CA4, &h7AE94FA3, &h50193E15, &h5E2ADADB, &hC328ED72
Data &h0743D205, &h8E2ADDD1, &h43197B37, &hFEC0FDA4, &hB8825D96, &hC2F95DB3
Data &h8803C6E5, &hE30C01D4, &hE1345304, &h67F44F4D, &hE19FF15D, &h2EDEA1F2
Data &h30F48EB8, &h1EB4909B, &hA60CC875, &hF590030B, &h7CB3D2DC, &hC8DED110
Data &h1ED986F3, &h2625815A, &h74EDB09B, &h53C7D95D, &h247AA7BF, &hC2689F78
Data &hA705EBC7, &h97830CD3, &h98D93596, &hC1FF1580, &h338E1E07, &h1C2837FB
Data &h35CCD692, &h10C835A0, &h6CD827B7, &h98307A0D, &h0C8477C3, &h9443E2DD
Data &h3659F5C2, &h6151603B, &h5A9E2C0E, &h0BE42DFD, &hAC0441FD, &hE3B9D4D5
Data &h4DFB02FD, &hE0DD43D6, &h3C712534, &h6F5C4F8A, &h5E7D5107, &h42132D98
Data &h9AFE790A, &h478AB9CD, &hAEF1D791, &h61293C41, &h8258B03B, &hE9E85DED
Data &h03AAFA95, &hFBC155EA, &h635E06C0, &hEFBE0998, &hC7C9C772, &h66D66AFE
Data &h3B6E9613, &hD661CFB5, &h847CCE79, &h5EC33A52, &h9D00791C, &h860E72B1
Data &h71250B37, &hBCDDD6D5, &h8C4C2B1A, &h53A8CDE2, &h2D754E12, &hED4CEAB1
Data &h751AF6A2, &h839CD3C8, &h28786DB6, &hDAA157C1, &h68F69104, &hA1742163
Data &h7308F767, &h6181EA41, &hA2B0926D, &h750C6DA0, &h30134092, &h5E874102
Data &hC09A0280, &h90255586, &h82C5305D, &hD20B4136, &h7C5FA257, &hCA66A5A5
Data &hE74AF3F8, &hA772AA08, &h0C1DA0E9, &h64459BA4, &h23992830, &hB38147B6
Data &hEBD68E89, &hE6FC2967, &hFD32BEE7, &h751BF962, &hAF86EAE0, &hC18C93F6
Data &hF505EFE2, &hEB4DB3D7, &hECED65BD, &h70B25F7B, &h427C2844, &hBD8D260D
Data &h76A46678, &h4A67F2FA, &h1B824DD6, &hA88A7C87, &hEB8012C0, &hA39A12CB
Data &hB5181627, &hDC3E4131, &h8F27E792, &h6925F239, &h508E528B, &hBC81280C
Data &hB37C6ED0, &h30F63E0A, &hD2273749, &h1123CCDE, &h685F0895, &h4774715A
Data &h53270EFE, &hA7C07361, &h987EB9E8, &hDD44B0DD, &h10038EAA, &h666D52E2
Data &h98B6C241, &h0CD9DF76, &h63803320, &h2D4ADECD, &h648222F4, &h699C14C2
Data &hB88F546F, &h79F4818E, &h465BEA9E, &h5492E836, &hD207B053, &hF59DAB59
Data &h7AA85CAC, &hE20EBC3F, &hCEA51068, &h26DF488A, &h4522F18F, &hE564A398
Data &hD4DAE8FC, &h49F5FE26, &h9179C2DC, &h2FA83A3B, &hD731A17B, &h5A1DF76C
Data &hC5E15590, &h9694A353, &hB5F9662A, &hB9D20E3F, &h31EF8B48, &h21BC5501
Data &h909CDEB6, &h81D8D989, &hB2BA037E, &h8473603E, &hDE6B1961, &hFEBD08BE
Data &h6DC75B7F, &hEFEF4C44, &hD6E14304, &h16BDD666, &hF60BDED7, &h0C87200D
Data &h3A0BAC75, &h147A54E3, &h2462C6B2, &h00E7BBAD, &h54F842B9, &hAE143F20
Data &hC476E97C, &hBB52A17F, &h9BF8A25C, &h9660CEDB, &hF1016D2F, &h84CFC596
Data &h434B0C1C, &h2C886F82, &h575E407E, &hD838CAA7, &h4B59BB1F, &h9C3B38D8
Data &h847456E0, &h22D46F0B, &hBC5299A8, &hCE5493C0, &h288BCC61, &h82319195
Data &h68B81745, &hF74BD872, &hC1F0F8C3, &h8698A21E, &h53A5824A, &h89F8034C
Data &hB94594A5, &h7CE36698, &hA1405CDD, &h0E01B34A, &h039768EF, &hADE46F97
Data &h9881524B, &h8641D828, &h51691875, &hDA706B1A, &h75573E3D, &hBA2EF286
Data &h3BD8E36D, &h64431B47, &hEBB01588, &h83E14BD0, &h25B0E13E, &h607AB570
Data &h8F8078CD, &hB5C00CCA, &hB9A954E4, &hF1062C93, &hDDD5F830, &hA2DB6C63
Data &hD4AD50ED, &h0498E7AC, &h557399B4, &h7D44D4B5, &hC4BE6EDE, &hB2678B77
Data &hFDEDC94E, &h4757A1B3, &hF094172F, &h219AA6A3, &hBEF97E98, &hDB7A92B7
Data &h68022D34, &h9DEBBFD9, &hA9364474, &h48F49018, &hAA51018E, &h9931BCD1
Data &h6EC7C1F8, &h0261BC83, &h6751EEDD, &h2656E1F7, &h5515B197, &h323BD147
Data &hB2B7D9FE, &hC7CCC51C, &h4FA734F3, &h25EC739A, &h9541A2FB, &h75C9E97D
Data &hC13D1672, &h01C2341B, &h5EE4B872, &h7AC12CB4, &hE848CD54, &h3DC82A21
Data &h8C05AAEF, &hE69DC784, &hF327573A, &hFA4B7E1E, &h27F8D8F8, &h2E90960F
Data &h3499CAC3, &hF601F134, &h7AB2686C, &h7147382E, &hC91B6534, &h3859BF92
Data &h4E8404A9, &h412A814E, &h6DE6DEBF, &h2144E23E, &h9B88B8E8, &h0BBD01D4
Data &h016D07F5, &hF8F4EDD3, &h3BCBFAAB, &hDF28565C, &h8F24F7C1, &h5C92DB91
Data &h93CDBB1A, &h8607A62D, &h34A51D52, &h1973E10E, &h2ABA5A39, &h0303CA99
Data &h19DE0CE1, &h631898B2, &h0257D777, &hF1935FD0, &hF8896D17, &h9A3496ED
Data &hFE9A69F0, &hB6FFC8C1, &h846BE47E, &h98D6E05F, &hFF1D4663, &hCC701D4C
Data &h0DF2CA32, &h60291F64, &h7868B43F, &h39F71E01, &h67894A7E, &h72F0F985
Data &h5B5512E1, &h16B0F735, &hF672D85A, &h13BEB50A, &h7469F07D, &h8659EBE1
Data &hA3CD9CF2, &hCFC5606A, &hA6724056, &h14DAAB39, &h12ABD763, &hA6C9CC2A
Data &hF8DB7A6B, &h6A292619, &h11C2C8D1, &h0C2E4130, &h207B2DAC, &h266AA815
Data &h45C539A7, &h1FD9DDC4, &h5BD53669, &hED6FFAD0, &hBBA70A72, &h6E8C8789
Data &hD3826794, &hBAF167C0, &h9DEB5E1D, &h61EFD9A6, &hE11A5C63, &h59E6DB13
Data &h252FA924, &h1D69A906, &h2A40BC23, &h944E60D1, &h17D87452, &h159A57DA
Data &h29374AE7, &h9C3D48BB, &h700576DE, &h724A1C91, &hB8E0FF97, &h030EAFCC
Data &hF4C1ABC2, &hD17262FC, &h02576542, &hD560F0F6, &hD3FE801F, &h9F6E5324
Data &hE5BBE63D, &h1A5E7A9D, &h15D0C9F6, &h0FFC1511, &h9D3E0DDF, &hAD35106C
Data &hC8AFE589, &h9F78CF7E, &h53814202, &h763D0160, &h00477470, &h8A1DCC48
Data &h58EDB568, &hB0FB6D6F, &h3F196072, &h49B960DC, &h604373E3, &h27364E4B
Data &hE9C14EA3, &hDDB498C2, &h0E90FB22, &h1E7E0389, &hD1173896, &h03FAC97F
Data &hEFD90BB2, &h57BBD0C4, &hF36DFA6F, &h6E3588BE, &h74733508, &hA3592C9F
Data &h8876D03B, &hE27F97E9, &h38C80FEA, &hD11C14A9, &hBB5C2A98, &hA70B1240
Data &hEB28BFE7, &h2E0DC803, &hD2E211C9, &h12A972DD, &h70F70ABB, &h6B074D15
Data &h6757E315, &h80E18C6C, &h0899289E, &hA2231052, &h4BD9E760, &h3CEEB102
Data &h94E16A2F, &h1ABF872D, &h686A13EC, &hEF0B0A6B, &h2272A1C7, &hA2B5074E
Data &h4CBCE322, &h3CB143E6, &hD24D68A2, &h1818315C, &h614E4293, &h926B7BF6
Data &hCF753825, &h461E1892, &h17ABCC47, &hB0A6D2A4, &h03B1F76C, &hA5574A0B
Data &h1C1EBEA7, &hCE8E2555, &hF9B11392, &hF9306B0A, &hC04B1991, &h457BBF2C
Data &hBE555B0B, &h594776A3, &h47A8EFFD, &hB488AE0A, &h88C53CD3, &hAE461EEA
Data &h4121E62A, &hD3BC97BF, &h18DDC8AB, &h6BB01145, &hA100D068, &hC61A4B23
Data &h912CA23D, &h15B966F0, &h462F3D65, &h86F7BFCD, &hA79B7316, &h64CE8929
Data &hF83A3975, &hFB9B4F7B, &h49CA1D47, &hF8F8ADDB, &hA10ED562, &hFF043AC5
Data &h92AAEFAB, &h607AD303, &h3FFE2E24, &h4ABFED6E, &h9BB60179, &h73AD3B3F
Data &h3E11EA60, &h8F227576, &h598677A5, &hBA087527, &h0018B770, &hFB62B67F
Data &h63EBD661, &h50E9AD96, &h13FC162B, &h0A7CD00C, &hA5A9BE32, &h50A1F2ED
Data &hC7B17328, &hB641AF00, &h48AF6A9F, &hE920F89D, &h314B8F87, &hE29593D7
Data &h11629F78, &hF4E99C86, &h8DB4C3ED, &h09E57A0F, &h52FABFBC, &h71B1EAFC
Data &hDBC3437F, &h28CDB66D, &h6BFFE534, &hDD29F51F, &hC3F9225F, &h25685C56
Data &hCDAE22D8, &h353562BC, &h55DFD36E, &h4C1E8886, &h012F15E4, &h03F33638
Data &hEC5429A3, &hB29F8E3F, &h31084A6E, &h17BC49A6, &hC28D2C43, &hA7652D35
Data &h97FE9723, &h4499C105, &hCA905F69, &h880582DC, &h4FBB2410, &h05F2C8A5
Data &h1DD4E1C4, &h2D0468B6, &h3F45E617, &h96AC67DC, &h8C1B33FD, &h8EC8BCAA
Data &hAB100B20, &h7386EA1F, &h37D241D5, &h659F18A2, &h36DB875D, &h09BA491D
Data &h9E8104AC, &h7D244C9B, &h6C83FE50, &h55388709, &h611370F4, &h54CE7155
Data &h1DC1428C, &hEAF3724F, &h69BE2532, &h5ED24D91, &h1A46CDEE, &h2693D898
Data &h4C80A5C3, &h678E1CF9, &h1FC66F56, &h971C0800, &h3BA19D4C, &hAE327F74
Data &h1015F997, &hA559FE90, &hA9DF7F5B, &h692ADC94, &h1A6DC30F, &h382CECBD
Data &h2F20A62B, &h639A0DC2, &hA9ABF04B, &hEBF36A3B, &h524719E3, &h17D80B0C
Data &h870C8EAB, &hCA817B1F, &hF71E746E, &h09E04283, &h1305563A, &h0312B699
Data &h13E5DE42, &hD2307220, &hEFA3ACE7, &hEA247AC6, &h2D9415F0, &hA0BFDA25
Data &h338DF8EE, &h7B2BF3AB, &hEBB01003, &h3138FE66, &h731F56EE, &hE49B4F96
Data &h9F084B01, &h6A995193, &h60B5D2E1, &h33429E07, &hE2F86059, &hB69D0132
Data &hE7EFECB4, &h2BE10E4D, &hDD20C299, &h6F6FC2D1, &hA0788E9B, &h9C744748
Data &h6946F60E, &h028A5FEF, &hE44CD898, &h8673B9F4, &h7E62D2E0, &h2E3A6410
Data &hBA10D28E, &h2A203318, &h3C79C2EA, &hA6100AE6, &h23369921, &h909B3E36
Data &hC2D66146, &h52CBEB3C, &h9AA28ACD, &h1D2626A4, &h0FCC700B, &h7E9A0BDD
Data &h3BEA9A57, &hAC7A5A9E, &h26115A60, &h0E0AADB6, &hF89CB0AF, &hB5365078
Data &hFEDE9EC6, &hCC3B2815, &h3F20DF3F, &h835057D7, &h2B9A5F6F, &h9BB8F3B7
Data &hC3F165B3, &h0ED03910, &hE72F927E, &h3C02AF85, &hCCAAB358, &hB03AFF20
Data &hB79C085E, &h58BEBDF3, &h1D8FA028, &h85D4F6CC, &hDA377FFB, &h89E9DF53
Data &h058C9871, &hDB8A0314, &h68DADCD3, &hA9DD8781, &hCEA4D3EC, &h9DC99957
Data &h301EE1FB, &hF2943011, &hA9F9CBDB, &h7A0F2157, &hD2FA518D, &h4323E695
Data &h5F698AFC, &h4DFC07F1, &hD5BFEDDE, &h188BC135, &h56162DA7, &hA62D7735
Data &hF1CAAF7F, &h5A8DDD13, &hAA031A64, &h103A08E2, &h767BE653, &hE1A6F6FC
Data &h6D8957E1, &h0A4E041F, &h94D67EE8, &h27D7CB09, &h8AF255BF, &hD1C05031
Data &h6B945C4F, &h99768D98, &h27ADDB78, &h2C52CC8E, &hA0BE0E69, &h1A606061
Data &h3BB06983, &h87C6DC50, &h56D5F525, &h6B75A4E3, &h556281C2, &h92685750
Data &hA830302D, &hCBE72797, &h6743DA06, &hA328DAA9, &h2B9620E3, &hB6736CFE
Data &h906CF224, &h929A05CD, &hFBCFD5B6, &h9E371467, &h0AB7CC90, &hA0541C32
Data &h61DF1A90, &h30AAA013, &h3D55E23F, &hDF980A7C, &h97B112CF, &h89061F4E
Data &hC9560B50, &h2129F8D3, &hAE38E94E, &hB3464F36, &h7AD3C263, &h224AECEC
Data &h618C780E, &h7FE28F6D, &h6D3D88D1, &h52449927, &h93CDE56A, &hD55DD7C8
Data &h6C8D2E31, &hA75CCBDA, &h1DD33A86, &hAA8CCDFC, &h93E72FE1, &h3FD5B76A
Data &h48705C13, &h45D2DA09, &h31094CAD, &h8BA32AB2, &h50B81F50, &h3EA07CC6
Data &h34365548, &hFB2A61EA, &h3FD3CFB3, &hFD340293, &h65B56235, &h1E165586
Data &h1CEF33B8, &h05CA78DE, &hB6037C5C, &h14D3475B, &h759CC081, &hE9F01F3D
Data &h5AE1C7FF, &h519DF82F, &h7CF9F9C5, &h64FC8DDE, &hD420EC8D, &h7FF825A2
Data &hE7EBBCCB, &h4AC434C7, &h318BD4C7, &h0007D61A, &hB44B0CB4, &hF22D80CB
Data &h39292F01, &hB4F27EEF, &hAEDC2D84, &h7915558F, &hEBBA1D7A, &hFAC4F0BD
Data &h8BB262F3, &h7F664C96, &hE762D9CB, &h2951550C, &h0C28D45C, &h2841F966
Data &h0E40DF9B, &hFA03E2B8, &h9C27244B, &hCD0646DA, &hA75178C9, &h949B1466
Data &hC83B4202, &h3AAD08B6, &hE3EDBD27, &h2AE3B3E6, &h0AC73CDA, &hB5C6021B
Data &h487D8354, &hFC619913, &hC2A25815, &h8EE5ACB7, &hDC6BC239, &hA1791702
Data &h8F29A758, &h25376D6F, &hFB04EBCE, &hD3328FA3, &hEDA179A8, &h9FD73E91
Data &h6A8F5110, &h7D288CC0, &h9B50C2E3, &h5F926AB7, &hA9BBD56A, &h8AF23560
Data &hCF5A7067, &hD46A0444, &h543AC50F, &hB20B49AD, &h844F10E6, &hEC723DD5
Data &h1183110B, &h089CBA6C, &h8416C944, &h03D8F9FC, &h8661AA8D, &h76DFBC65
Data &h61106E2D, &hE8500AC8, &h8DD171D4, &h677990E3, &h928B87DC, &h2892F785
Data &h99C62B27, &hF7ED02A8, &h2F4EFF60, &h489A258B, &hCB9C0DCA, &h66B9BD07
Data &hE143C150, &h68F589C2, &h77A7346B, &h5176AD47, &hA48A2A0D, &hA7753661
Data &h10F0C57D, &h7B2C9475, &h595F6BAD, &hD3BE79B5, &hDEDE7EE4, &h13FACD81
Data &h69E6C59F, &hFE3307CB, &hEA33703B, &hB3A4E38B, &h271817D7, &h349DFB04
Data &h8D5FB965, &h9C3F5DE9, &h2F32637F, &h00DAA972, &hDEA6E0EA, &h803C732E
Data &h12537CE5, &h3059C48E, &hF6125BE5, &h8376177A, &hE7C42966, &hADB5DCED
Data &h589E08B0, &h6360B0DA, &h9A344BBF, &hDD55EE6B, &h35B4808E, &h930B2A32
Data &h64BB4DAF, &hFCC3C117, &h6307229E, &h45048CF4, &h05BA547C, &hE2CF6F1E
Data &h14A538F2, &h93F5CBD9, &hAB2CE5FB, &h0AA91384, &h08896586, &hFF0BBD7E
Data &hBD3AD34E, &hB0CF9DAA, &h80EFCC48, &hB16E1C01, &hB777464C, &h046A415B
Data &h962F5FCC, &h400A4FE3, &hE02A2C5D, &h425C5C06, &h6F93EF72, &hA35EDCB7
Data &h634D79A3, &h6D2B9577, &h98C80B2D, &h81D32E01, &h11BA3619, &hD2AE9F16
Data &h3B65543A, &h6A8D2F4E, &h77BBA901, &hDCD6BAB4, &h68C5AF21, &hFCF99032
Data &h1EB1A523, &h4F7D924E, &h4FF81BCF, &h2EF6AA41, &h98518C5E, &h20CAA579
Data &h8768CF86, &hCC1CB360, &hBDB22A0A, &h633440C9, &hC354D510, &h38BF290A
Data &hE4E1887F, &h609183DB, &hA42C464D, &hEF224EFA, &hC95EB470, &hEAA2B406
Data &h4A66A98C, &h62C135C6, &hCBFE4329, &hFC1DD0E9, &hC8EA3458, &h7E186B6A
Data &h1470B78C, &h4DED95A5, &h731D1F44, &h7ECF49BC, &h37725FAD, &h22662D1F
Data &hBE1DB543, &h4B77A0D6, &h5132B2BF, &h4A6E24CC, &h21749325, &h95E2A564
Data &h78BB63FF, &h05CFF753, &h614D27DB, &h287A049D, &h4E40219B, &hC000E9F8
Data &h9EB09EE0, &hB290ED30, &h1C89A029, &h18FE5335, &h4A18901C, &h4DDF246F
Data &hC7D9851B, &h2E28B321, &hA48053C7, &hCF7E4EE3, &h9374879B, &h166439BF
Data &h24D9D3B9, &h7DC6AEB9, &hADE4E71E, &hC36046AB, &h6BBE5BBC, &h78B7CE37
Data &h927910EB, &h56DEB73B, &h02B3BDC4, &hB64C4BA0, &h38877620, &hE382F426
Data &hAC77AB7D, &hF5409F49, &hC9100DEF, &h1F6BE031, &h0824E944, &h883F8EA9
Data &hB2618277, &h13D467D8, &h9DCD47A5, &h7FEF76BE, &hB9BCDF5D, &h7B2071C9
Data &h986AA269, &h024C5BC2, &hA7BDB418, &h328DF7B5, &h845630FD, &h935F9B86
Data &hBDDAE64A, &h76E2B816, &hF843D168, &h28EAA407, &h72E31D5E, &hB37FC549
Data &hF81FEF47, &h18F396DB, &hC35AFB31, &hFDD8D987, &hC83CA4DD, &hF98C5BB6
Data &hE0E65CDD, &h11A2FE02, &h9DDC1F9C, &hA286AE7B, &hB872D9EF, &h59A63A0E
Data &h6C1E8A11, &h9D9FA543, &h9B545865, &h2169AACF, &hEF20198D, &hCF6F2452
Data &hEF0D9DE0, &hD121B1DC, &h53DA2ECD, &h86BA7F1F, &hB1CC4D98, &hF655B02D
Data &h2182FCAC, &h9B837221, &hB3610830, &h89B5458A, &h921644A6, &h7DF0908C
Data &hBE6DF598, &hFB120F3C, &h0FC5680B, &h4112A2A3, &h864E285A, &hEA8B7323
Data &hF3ABCC90, &h2AA8EF4A, &h0FBBFFC0, &h0D1115E9, &h968DB4F9, &h75B3901B
Data &h44273219, &h35A19977, &h4331EC7C, &hCBADFAE8, &h41A5042A, &hD165A1AC
Data &h5DE263CB, &h984279B0, &h09D2D5EB, &h7E5EED5C, &hBF103599, &h7ACA5F4D
Data &h30747E85, &h77B712BF, &h0D44D12E, &h2138051B, &hAB87C6EE, &h447B88A9
Data &h594B5DA5, &hB156B8C0, &h4936B5A2, &h76A865D7, &h856CD593, &hD1C54560
Data &hC1D9C1C0, &h33E19F6C, &h3C38AC9B, &hDF9EF168, &h11FF4F35, &h92730EE6
Data &h26166FB7, &hC4197B4A, &h03BE3298, &h09635287, &hDF8C43C9, &h7FD1C5EA
Data &h3AA93218, &h7FA67749, &h605F78FE, &h2C0E3E1F, &h7B185234, &h68234D7F
Data &hB4F89852, &hFE803A51, &hF96D8BA7, &hB966735F, &hBB1A3EA9, &h9029AAC9
Data &hD8800940, &h7AF142C3, &h06EC7E3E, &h8CC862A4, &h88111975, &h28864EB9
Data &hB922B6A5, &h14A83A7E, &h5AAA3D85, &h4DC6794D, &hD9A285BA, &h308AE623
Data &h75235454, &h66102431, &hF966D73F, &h231705D1, &hEA15FAE2, &h701BC836
Data &h782A4EF8, &hFD0903B5, &hFFB8D1F0, &h083CC0DA, &hB062A47C, &h9A834877
Data &h9E74F3FE, &hB523F731, &h9968D7A9, &hF1D5B8F4, &hDD523D03, &h363F851A
Data &hCBA5A48B, &hFEE73DBB, &h5B766BA1, &h693BC044, &hDA678D72, &h4887DC40
Data &h72CECC11, &hDE6B84D8, &h57C07284, &h927EA505, &h33FCF183, &h12031D59
Data &h633DE84D, &h79B0997E, &h57FDD626, &h75B411CD, &h78819D84, &h9D655269
Data &h102BFC6A, &h87307F41, &hB8919FE4, &h452BB546, &hB03BACA2, &h1FCE0855
Data &h6827DF96, &hCABC9C55, &h89A75745, &hB30F8B3C, &h508137CA, &h2422075D
Data &h0CEC8B3A, &h1A031BCD, &hD7932801, &h23F60E56, &hF094DB51, &hAE66F2BA
Data &h79793ADF, &h697B8961, &h338AC5B3, &hAFC2B26A, &h13A5CE65, &hA4EFFA43
Data &hFE38FDD3, &hD58888AD, &hE04B7096, &hACB71BE5, &h911E958A, &h3DA332C1
Data &hE1444F44, &h972919F6, &h1C1C27C7, &h57912EC5, &hFA8CF67A, &hA753B84B
Data &h58082DE5, &h558C03EA, &h0F27D8D1, &h19C2596F, &h48F3ABA3, &h25DD9F80
Data &hB6012D33, &hD9CB9F75, &hD9885031, &hF5A61A92, &h82C310E3, &h4128FD93
Data &hA23E9E88, &h90A361C0, &h30B0F108, &h6B880B31, &h9B213DE9, &h71BFE936
Data &h55C5990B, &h531AE4B4, &hB56C4690, &h32AA2E28, &h63EF06DF, &hECC26159
Data &hF0B870D4, &h7D145241, &h276BA756, &h3073B6A0, &h015E8C60, &h0AFF0ECB
Data &hDE63AAC0, &h39C141BF, &h99603ECA, &h792D6DA6, &h8CDD7873, &h28B77E2A
Data &hD91B0FF7, &h6F33F5CB, &h20BB8E3D, &h4DFF634D, &hBD783D62, &hADB89CCF
Data &hD838DF55, &h1D2C4411, &h2F110229, &hDB345233, &h50BBE6AA, &hD946004A
Data &hEF346FDB, &h95C3B961, &hA53348C3, &hC292EB0B, &h3E991083, &h98D78B0F
Data &hB01822BB, &hE7D4FF52, &h1DEDFD7D, &h168D8BB5, &h3ACA7208, &hBF60D494
Data &h60920B3E, &h91C80ED5, &hA758F834, &h66B82527, &h84568990, &h533F9BD0
Data &h6D2F6118, &hE3265A8B, &hB559955F, &h5891E496, &hCDFDB34F, &hB043A079
Data &hC3C8E7C5, &hCF100355, &h91732817, &h34FD4270, &h551DAD0C, &h75C25465
Data &h9B5B87DD, &h6DC46537, &hB0A77825, &h7EDFDB3F, &hE9477884, &h450A78FF
Data &h9FCA224F, &hAF596B95, &h122CF537, &hE580FBCD, &hD94A2B80, &h077ADAB1
Data &h8FA3CCB0, &hBE48175F, &h778B44DD, &h68A1638D, &h587B864D, &h97CF2C29
Data &h4F239C24, &h0994703B, &h5A32C60B, &h23C5CB89, &h008BA208, &h8AAE66E8
Data &h1E3708A5, &h64B46E56, &h7E76DF95, &hFF8C4675, &h3A67701E, &h6CE33D1B
Data &h2F3A10F3, &hF6DCE1F9, &h15ED8F5C, &hD0CD3F62, &h0ED8ADBE, &h1B388D82
Data &h605D2E4C, &h2021E94B, &hCAFB659A, &h0C227B9B, &hFC355AB9, &h5AE5C1A2
Data &hE233A57E, &h5A1A5249, &h6CA7FE3B, &h2B5729B7, &hE0AE1710, &h86BF002B
Data &hD7602F53, &h4E261A1B, &h5E9AD956, &h9490C529, &h9928B1D8, &h449B8E62
Data &h75889056, &hAC9217F3, &h361D32E9, &h1DDBCD13, &h4DA3504F, &hAB60FD56
Data &h60AFC001, &hADE34FE8, &hB046B5DD, &hF8F6ECD3, &hF731997A, &hD07A19A3
Data &hFF4D43DA, &hD21E697D, &hF502C648, &hF7146B3C, &h4401A02B, &h4DC1B26C
Data &h61BB53C9, &hAAA9CC49, &hE8DE75DD, &hCC4C4055, &h42852A47, &hE6FA87F8
Data &h537F8D63, &h2F02F797, &h251721A7, &h188F2DCA, &h20D1254B, &h399A4E7B
Data &hE5EDF3C5, &h73FB2813, &h1B0023A4, &h81CD76F9, &h5C4B178E, &hCF703B63
Data &hDB27D2DC, &h36B48B91, &h600C4518, &h19425D5C, &hCC219106, &h577DA549
Data &h0B77F114, &h2AB70B57, &h7B49AAC7, &h23839030, &h11AA51A7, &hBA51ADDF
Data &hEFCE3A2A, &hC8686B14, &hD38D47DA, &hFB08F7D3, &hEE42868E, &h57BE37C2
Data &hECAED2DC, &h2F011E3A, &h31A0115E, &hBCBEB578, &h0F67169F, &hBC6BC2F8
Data &hF66FDF56, &h83A85611, &h1EC1BE6B, &hFF08BFB2, &h9B9846CA, &hA04D1446
Data &h8BC11D6A, &hC49A8C8E, &hD7ECC055, &h16804997, &h78FF3D99, &h3ECEEBA9
Data &h49C35F16, &hFE2A82D9, &h84A56A1B, &hCFEEF83A, &h1D0E1ED9, &h42EEB7A2
Data &h800F2E48, &hA6D984BC, &hC8EBD2D1, &h0A403338, &h85B489AA, &hC70350F5
Data &hA9327A0C, &hC45511E2, &h7262746B, &hF773FEC3, &h94A8FE28, &hD2CD8C38
Data &hE86281A5, &h9A71FA45, &h4E6173F2, &hB410F806, &h39A95072, &h740E35DE
Data &hA940947C, &h677ECAA0, &hC4F52F4D, &hBF5C70A8, &h2AD15BA0, &h7D9E3457
Data &hEDDD6345, &hF6EA4C8C, &h77D6104B, &h14C5DF96, &hF081227F, &h6317D8A1
Data &h66066CC5, &hB1CAB574, &hDE296CFC, &hE97D12C9, &h5F9D34A6, &h117BB1DE
Data &h8875AA98, &h9C82C7F0, &h7F9C51A7, &h5EDB73F8, &hB7A254EE, &h2166CBDF
Data &h5DC6C6CE, &h1A8E695F, &hB49C553B, &h7CCAAC37, &hC07458B9, &hAAA64936
Data &hACD27395, &h8546C057, &h92EA983F, &hB0ADC1A1, &h037D4203, &h160F4747
Data &hADEDF404, &h51B1EDD1, &h1909D218, &hF17E91EB, &hDFBC1A53, &h42E69444
Data &h48E86774, &hF3DFB3D6, &hBB90A0FA, &hC50EA222, &h83EB3159, &h53D5792F
Data &h03806BD6, &hFA933228, &hC7E2081D, &hD9D8AF73, &hCDB1617F, &h9AC19F11
Data &hFE168CF7, &hE3223929, &h219C32FB, &h9AD87674, &h1C7C1145, &h9849CA25
Data &hD5115219, &h10D977F9, &hFFED4587, &hC5724A0D, &h53649BC6, &h54DFC7BC
Data &h9BE3E29C, &h74B51560, &hC0270865, &hD1439A13, &hA60CC1F8, &h42F029F3
Data &hF87775E7, &h29D72849, &h37C904DF, &hC662B9E3, &hED581F51, &hF5AE3AD2
Data &h90F8A520, &h5BA1CBE9, &h0DBA6C96, &h724E12E3, &h4B4319C0, &h330E6CB7
Data &h4E3D030F, &h5FB1C7B0, &h8301CA14, &h17B46A87, &hFD3B9578, &h234C3A18
Data &h81C501A0, &hDA97A24D, &h82028957, &hD0E61E27, &h01C3EA0C, &hCBDE8769
Data &hBA47AD47, &h2DA7732A, &h955461A8, &h8402D9BD, &h59181CD8, &hF15C9129
Data &hF8F3CF18, &h3EA63745, &h4BA2EBB8, &h699AF354, &h0FD8DDDB, &h9C088968
Data &hFA88E7A7, &h07DF20E2, &h100BA573, &hDCBB7950, &h4C259761, &h9DC3FEEE
Data &hCCEE9CB1, &hC1AE8102, &hA3BFD8B9, &h097486F4, &hCA5CFABD, &h27B530BF
Data &hA7C64F7A, &h23B178D8, &hA4FDDF2F, &h31B16141, &hE676A701, &h21BEBB8C
Data &h432A205D, &hA95F2CF9, &h12F0AD3F, &hA192EED9, &hB0D90409, &h55A5619D
Data &hA9141F56, &h79DC6D3A, &h715DE7B4, &hDC28C838, &hC99D2A46, &h78370F15
Data &hC40908C5, &h5193F647, &hE78D78BB, &h2B63D102, &h162989A7, &h782B72EA
Data &h88808BE7, &hBE09D25B, &h898CFDDF, &hEC473BB3, &hB41F41EE, &h616EDF74
Data &h95DD426B, &h76BC3644, &h31EB5E78, &hAEE54CD4, &h2B92ED83, &hEA8A8A87
Data &h72F82601, &hA9F06556, &hA6CEF9F8, &hDF22DEF9, &hBF0A90DF, &h71A702A4
Data &h643396A0, &h1D19F394, &h3ED620C8, &h903074A7, &hAC44201A, &h000B0926
Data &h389AD239, &hC51DA8A7, &h92533694, &h9340A0E7, &hB0C5E8F9, &h6D8FFB12
Data &hEC0D0D26, &hDB6456EA, &h20DAC262, &h1FC6D36A, &hA260A914, &hE80A2295
Data &h24D0CE65, &hBEFC39B5, &h2EFFF3D1, &hFE38054A, &h93458C74, &hF859F7BC
Data &h3A693CAB, &h7BAE2199, &h65456D27, &hDC2E68B9, &hA334C50D, &h6F7FCFF7
Data &h242C83EB, &h6277E850, &h6724AEBA, &h29242576, &h773ABE18, &hD7553A73
Data &h8AA26900, &hAC9FF8FD, &hFE75CD8D, &hFC2087A2, &hB6918D21, &hBD819195
Data &hD1045016, &hAA678F21, &h0C88D0DA, &h03F735A6, &h0072FF2F, &h621C91C9
Data &h4201B12E, &hCBDDCB1F, &h30F36649, &hDA1320FC, &h98ACD9DF, &h44FBEC52
Data &hFB8EF384, &hFB8FF28C, &h76142D8B, &hEA419EA5, &h6B8B9C06, &hBE632E5B
Data &h4332473A, &h36500289, &hCEB3CBC2, &h7E02A99D, &h69E30E84, &h1E504FC1
Data &h3C1F58A7, &hF703D3E2, &h5D2A261B, &h4A97F982, &hEC194991, &hBF587ED9
Data &h5F7BB9AA, &hD590E4C2, &hC7F3861A, &h7ED60B98, &hC2D38C09, &hCFA691D6
Data &h3B0A683E, &h3649A275, &hB2B7FC4D, &h1F667EC3, &h88223685, &hCA32E6D1
Data &h806C61A9, &hD7592487, &h7DF4F6FF, &h3F778D9E, &hEF38CD32, &hDE7FA317
Data &h3EC7CC6F, &hD284D2DB, &h913F4679, &hDD019506, &h77D7A55F, &h2AC56AE5
Data &h69648643, &h5CF4AD42, &h05C116C8, &h347B29AA, &hC0F6E0A8, &hE0B3B3CD
Data &h245B2E6F, &h770D9269, &hD99FF3D9, &h006BC17D, &h8C4D8807, &h82B329B5
Data &h402464BE, &h1D9E2164, &h0F88DA6D, &hE84FAEA8, &hDA82CADC, &h48873675
Data &h12464F3B, &h0A25BC08, &h36050BCC, &h853006EF, &hFE571570, &hB160CFBC
Data &h5D42449D, &hED9F5D80, &hE55A4336, &h123ADA4C, &hEFAC549A, &h00E44C88
Data &hC8D24B29, &h1F5BD1AF, &hFC8B79F6, &hD6B244AD, &h3D525EB8, &h9B453DB3
Data &hF4AD082F, &hC51ABCF5, &h2A68B793, &h663EA39B, &h974E72EF, &h3919B3C3
Data &hB683FC25, &hDCAF3AC2, &hC1EA24B9, &h09B0A689, &h4386A782, &h504CAED2
Data &h3A09EBD7, &h1D3F7EC1, &h6105A7C6, &h7C51996B, &h6936C9E2, &h86A6D3D1
Data &hA79DEABE, &h459EACB9, &hAD09E281, &h9E0A916A, &h5A3AC9F1, &hA4DF9292
Data &h2C4316E8, &h1C868F30, &h8E1A7BBC, &hDDB8BC30, &h4672EDBB, &h212E3DA5
Data &hE330800E, &h5E187402, &hE36D9361, &h51AD5A89, &hACA0610A, &h0008782E
Data &h6966A21A, &h0F817511, &h0FE5DE69, &h6535795B, &hC06C5B33, &hBC0BBD44
Data &hF3C2E541, &h998BA3A8, &hEA484CD6, &h4405BBCC, &hD3139387, &h1CD3BEE1
Data &h7157A9B2, &h73943A2E, &h3B4D4678, &h30F6AAA7, &h028BF920, &hECE3903A
Data &h9408AD99, &h7BDA90E2, &hA87B348A, &hEBBD6C4E, &h5D6D37D7, &hBBD9460B
Data &hB5A90823, &h0EFC7D18, &h0AE5D040, &h832466B6, &hD5FBC024, &h82F5135D
Data &h50D3C86E, &hE2A89A36, &hD931F69A, &h078FEA79, &h4FDEF8BA, &h71A1553A
Data &hC3CB4FB9, &hE6152ABB, &h1E12C5A5, &hB1846A7C, &hAD1C09CA, &h0A4606EE
Data &h9B23B99E, &h3072AA63, &hC0DA5B56, &hD921F6FC, &h2F75AC39, &h4178BDE2
Data &h82A18785, &h8E90FB53, &h32A2F53C, &hBB5502FC, &hFB1A275C, &h583B9281
Data &h260C64F6, &h6F9503A8, &hABEAC3E3, &h8B3230FC, &hFE970C3D, &h4C23E30F
Data &h61B3265F, &hDB2087E0, &h882C30D9, &h813CFCFB, &h1FBDABDD, &h5681CB06
Data &hC97D0303, &h582A2325, &h20F4AB06, &hA02A26A3, &h0C2A2BCD, &hA4F5403C
Data &hA31BF6D0, &h55FFA44C, &h328B88B7, &h4AF5920B, &hF0C999EA, &h671C90E5
Data &h42C473C9, &h55284BFB, &h7DC03BB6, &h67FE7BA9, &h5F9AF963, &h49D77A43
Data &h528D57DC, &h0B5C8A46, &h3E26CE04, &hB5511DD6, &hD0B3CD9A, &hBEB6B7E9
Data &h32D1D558, &h2A287225, &h9377B258, &h6C83A85A, &h9B091E6F, &h59EFA4AE
Data &h3B3C26A6, &hBFF7F810, &h592F299C, &h97D33C2B, &hA5A02DBE, &h7CE4F0A6
Data &h69C5E7F9, &h12134E80, &hD6DD2045, &hDC899A47, &hBB61D938, &hB4A97C09
Data &h4473A985, &hE3FBA541, &h35AB85DE, &h76226C9C, &hB146947B, &h8D6BA521
Data &hCF39325C, &h02455430, &hADF41638, &h9EB129E6, &hEE43A4A9, &hF214F4D1
Data &h15811702, &h81F683B6, &hB61948D9, &hD7FC8576, &h33348477, &hF228653C
Data &hFDF6FD44, &h4E83BBBF, &hB803E8D2, &hEEA00D49, &hE3793A81, &hF5AD79EB
Data &h424A6E5D, &hAA2F31B4, &h95C23E22, &h7384A0F9, &hAACA31F2, &hE252C751
Data &hD285C3A4, &hBE34B431, &hCA9714AE, &h5419829E, &hC06F1D78, &hAF826A9C
Data &hEEF7DB68, &h077E53DC, &h9F377FB2, &h64501A48, &hC05E347A, &h429980AE
Data &hE2C34D3C, &hDA3E675D, &h707ECA75, &h86CAEEE0, &hC739627A, &h7E90FDDA
Data &h8C71A285, &hADEDE1F6, &h7D0AB5D6, &hAA5A6A63, &hE236EBA8, &h6B67959E
Data &hD1DA8B07, &h3CA8944D, &h68119933, &h7DD40CAE, &h4649809F, &h6B0894F4
Data &h7A894EA8, &hFA67BCAE, &h929F6056, &h54445FF9, &hEA3B135E, &hF1207B0A
Data &hF3450454, &h4CDAD9E9, &hAAA0B479, &h65C74338, &h48AD25AF, &h7177E205
Data &h45207BB0, &h06868641, &h1B3C66F5, &h7E9EBD46, &h75FAE2E6, &h28A3A39E
Data &h6F065AC7, &h4766B0F4, &hFFDD6A75, &h29C5DDDC, &h82DBB742, &hF8122D01
Data &h53AEE7DB, &h9E357C5E, &h6FBF38FD, &h801E4A70, &h6A44CDD4, &h10B04E94
Data &h4D557017, &hE167A527, &hF55EF906, &hD23296A4, &h258FC565, &hDC3217F8
Data &hFDE62C69, &hCA83D5A6, &h8DAD6D98, &h9BA1E4ED, &h50D6E33E, &h61301F7B
Data &h29E9DD9C, &hA65D5555, &hAB2D5AB8, &h7BADC903, &hE5E85EBF, &h7B3BDCA1
Data &h3B7718F3, &hA3595923, &h95791718, &h3F83E5E8, &hFDAB7F9D, &h5DED77EF
Data &h15037A69, &hE85C3D3B, &h708FD379, &hFCCEF088, &hF315D085, &hA1217CD4
Data &hEEA4D63D, &h52480683, &hD6C0E349, &hA2EB5992, &hEAD6290B, &h3E02E911
Data &h69D8F645, &hFE0F5C08, &hCF657813, &h574A4989, &h17E72FA9, &h2A16FDA0
Data &hE435BB84, &h407E1794, &hE0668117, &hAB3BF6F9, &h98EA7C98, &hCBDD99E8
Data &h7F07F716, &h188CF17E, &h2ED1B49C, &hA50A9F21, &h76346A30, &h41A45D2F
Data &h4EE4A88B, &h118F9FAB, &hF62748F1, &h75B1093E, &h9D92626B, &h38E89E67
Data &hCE05FB74, &h5B0BCA3A, &h940FB8CC, &h4F270DCD, &hBA8A877F, &hDD7B41F1
Data &hBEFD441C, &h248F436F, &h0E1ED3E7, &h4B40C9D6, &h2D4C7D67, &hF22A1082
Data &h1F26D10C, &h3269EA71, &h2EA254FA, &h09EBFEDD, &h6CD426F3, &hE1DDBD97
Data &h28C4A164, &h5EDC2CB3, &h6FBCECD4, &hC307C147, &h2BD0FEAA, &h315E72CA
Data &h652AB1BB, &h5B0E12DA, &hDA0C8B2F, &hC2059802, &hFF3E80B4, &h09F0CF06
Data &h5924A097, &h7AF96A1C, &hF16694E8, &hCC1F28B2, &h0C5DCF0A, &hFB1BA4E9
Data &h5C07734C, &hEEE433BD, &h869809A9, &hC7B696C1, &h6EF95B28, &hE1A9DB81
Data &hA31B2B44, &h2C09B5A3, &h35A4508B, &h406772DC, &hF86E31C9, &hDB1C5583
Data &h8D5D7284, &h2CB5A446, &h55880BDA, &hDD146097, &hFAB7F049, &hDCEE9ECA
Data &hAFDD1180, &hE273AAA9, &h2FD0ACDE, &h120D902E, &hCA8E9691, &hEC0FF069
Data &hB11A0215, &hF9D88132, &h2223933B, &h596F4782, &h44406996, &hB7A9C956
Data &h88121967, &h32ED1194, &h86BC90BB, &h55CB5300, &h3F4FB157, &h19878C04
Data &hA32BEB3F, &h86A06943, &hCB74AF40, &h1BCDD933, &h2F90BAB5, &h783BAD07
Data &h99A4DD3C, &h21CEC19C, &h5777465F, &hFB9F571F, &h31EF9918, &h0B93C0BF
Data &h2110C8CA, &hE21E7491, &hCCD20D6E, &hF4E6E9AA, &h1891E9CD, &hAA623285
Data &h471B3C7A, &hEC94196F, &hB0BF477B, &h08DF4BA6, &h5290D01A, &h585B4915
Data &hA6ADCDA8, &h912D3CD8, &hBECD9DB3, &hC4BFF697, &h8E5C6569, &h66889980
Data &h14040E6D, &hBCBE37C0, &hE5E274EA, &h352E9BFF, &h46A947DC, &h54C0A528
Data &h3533D6DA, &hA9022F3C, &hE4E7E33F, &hFC2BA5C7, &h7C4578D4, &h58DB3316
Data &h841C1FEF, &h5B88E734, &hE0F769C6, &hDD228554, &h4C90DE09, &h51588233
Data &h273E590F, &hE5C4E120, &h34C9FFC6, &hDDEB3E0C, &h00853BCE, &h0F083F19
Data &h541963EF, &hBDB01912, &hC4C1BD81, &hC8302B1D, &hC3A0026A, &h5B3A141F
Data &hBBF504B1, &hBB4AAF91, &h79A29003, &hD35EF7B6, &h4D4ED0B5, &h7042A6E0
Data &h090C8194, &h3BC7A71F, &hF028FAD6, &h988F4FFC, &h97B6D9F3, &h541B776B
Data &h113D7BD5, &hAEC67EC6, &h0B264FAE, &h13B2F43A, &hAF6DAB11, &h9BB2524A
Data &h130130DC, &hC8770273, &hB9EA148F, &h8B2270F6, &hD4369BD7, &h25CDFB0D
Data &h5DB7B334, &h7A8B1D1D, &h514C54F9, &h45DABD2D, &hEF84E89A, &h9897BC12
Data &hEE6606F4, &h6E36C32B, &hBF6A84ED, &h70ECAFC7, &hF97FC14B, &hEEB7BE13
Data &h1FC5C834, &h3EEA6F6D, &h5599D2CD, &h423BED47, &hC01A8181, &h01A990D9
Data &h655B1B15, &h928C8E05, &hDB1C901A, &hBF25F2CF, &h2D98F95D, &hDD527040
Data &hA1DB1F22, &h1346B2E0, &h2B20C6B4, &h90FEA5A6, &h9C472557, &h52AD9F2E
Data &hFB10F347, &hB7949C8E, &h811098A9, &h4A9A1D3A, &h7397731C, &h2DAAC926
Data &hAD3AFA3E, &h62DE5A0D, &h095447A5, &hE8BA8FE6, &hC4117AC1, &h9B765742
Data &h863278E4, &h58DD67FC, &h1698FD2E, &h70673D62, &hC78A9CD0, &h664DC966
Data &h9749CD6C, &h57A8A6A1, &h762165ED, &h893699BC, &h82962F33, &h3EF0390D
Data &h244D6D79, &h48386EC4, &h49C2F99A, &hD96F07C6, &hB771CE7D, &h216E25A0
Data &h41443481, &h675A8588, &hA9A71218, &h2BFB4E07, &h2C74DAD0, &hDDB767A9
Data &hC35C635D, &h2AECE5E2, &h14D5D08D, &h201576F5, &h77940186, &h97F917FB
Data &hEEF56806, &h5635C227, &h95C0D05D, &hAB9022DF, &h449C87D9, &h7796610B
Data &h1DF2DBCE, &h760E86D0, &h4D0FC400, &hD0A8A2E6, &h0A2C3486, &h9DDCEB0C
Data &hDA95CCCB, &hA6355C06, &h7631ECEA, &h98A32F07, &h9D0D8D4B, &hA3D053A6
Data &hEC01C6EC, &hB06AF129, &h353BBD67, &hA16D9E0E, &h963FAD96, &h01796229
Data &hE217CED1, &hEF1F59E5, &hC8742195, &h8506969A, &h5F0706A7, &h43D38328
Data &hEF98A54B, &h9A542EE6, &h517DC6BF, &hE2BA0E94, &hD78D4548, &hB261BEDB
Data &hFD37BF9B, &hC3269CBE, &hD0E607F8, &h4910B11E, &h681049FD, &hF5F33EBF
Data &h7CA61D17, &h40A36D8F, &h83CFB837, &h08E06F21, &h578F76F7, &h691CF1FC
Data &hEE96D288, &h91677963, &hFFA70623, &hD6B13450, &h15C3BB79, &h5C89A938
Data &h35D74A12, &hE104BD0B, &h71E345E0, &hF2721AE7, &h85080128, &hA2D66BCC
Data &hFEC39FBB, &h3583CB99, &hCE0FD992, &hF5D6477D, &hE1B411BE, &hCF9E861C
Data &h842A9EA8, &h8C58B5E0, &h61C09B2B, &hB81077E1, &h8DC86CB0, &h3A23AC69
Data &h34FBE245, &h19BC63DA, &h3F5636FB, &h8358F7B4, &hDA879F28, &h8B7E2A62
Data &h18658E47, &hEE399280, &hAD868E69, &hBBEA0FB7, &hA8CBB090, &hBBCFE05D
Data &h79EED9C6, &hBF6996A4, &h4656D154, &h1AF9A061, &hC6F9C213, &h9348355C
Data &h4A749D0C, &h8E1BA269, &h0CBA811A, &h596B78EA, &h5D138BB4, &h1B06003D
Data &hF479D305, &h1AC84866, &hDF2ACA62, &h5D4C0421, &h8C239CF5, &h4009D124
Data &hC04C3396, &h987182F0, &h79B018DD, &h7C3E2DAB, &hA19C91A0, &hB9ADB0DF
Data &hCE034C74, &h9DA3939E, &h2845A56A, &hCBACE4E0, &h22DADCE4, &hC2C52A5B
Data &hA0EC7F42, &h86D06BA2, &h6551092D, &h842419E6, &hFFF9D20F, &h457EBEA2
Data &h42F905AE, &hF454D6BE, &hB8C45BE8, &h8B749A9E, &hA2588DB3, &hE5B9BCE1
Data &hC24C2C3B, &h89DBF46E, &h76766D27, &h986D9AA0, &h9A7F15A0, &hE8E1AD8C
Data &h89F51DC6, &hA89FBE29, &h62579053, &h16810732, &h53816683, &h64AE3565
Data &h57FBC9A5, &hA5BD8452, &h5899A081, &hA5EA7F2B, &h767EC855, &h6BDFBFC2
Data &h2C0FB43D, &h6D42F70F, &h1EACD8B1, &h891AE93B, &hA72E4E78, &h3CEB10F9
Data &h31193FF0, &hEBAB2CC7, &hF5B0C0A0, &h007AE907, &hC4199211, &hB0DA9A7C
Data &h8A73B650, &h18B68D8C, &h73F29EB2, &h0C4A2584, &h37197B5D, &hA04E8A7C
Data &h5E65BF9E, &hA6A818F4, &h500B2C09, &hC6490BD6, &h947C3FCC, &hA11E62CD
Data &h33FA27A7, &hB37BD280, &h10E34300, &h7D630DFE, &h448BEC7B, &h5C9602C5
Data &h3FF9D95D, &h546301A5, &hA09515D7, &hC3D95C19, &h89ADE00F, &h26B7A9EE
Data &h35CFEED6, &h24FC22F8, &hDD635B00, &h3A1818CF, &h55B87B94, &h0A3BE6F7
Data &h66D0A512, &hEAEDEE63, &hA289ACE1, &h64C32564, &hF8712BC5, &hB1B02943
Data &hECA5426A, &h25ECB525, &hA33BC102, &h445664D2, &h72CA84FD, &hDC0C5576
Data &h017BEDF2, &h6F056E37, &h548A0E86, &hDE6D2304, &h0476D5F5, &h4414192E
Data &h69A56454, &hF918779F, &h0B84F4D6, &hD89E7EBD, &h0412EE6E, &hAAF20E4C
Data &h22021BFE, &hD824838E, &hB4CBB836, &h38F7844E, &h62B7AC3C, &h0F6071CB
Data &h013E7308, &hC931B10C, &h232935E1, &h998D4D4B, &h8545DA36, &h5DB94742
Data &hDD009143, &h3DB49E9D, &hCB4AA711, &h04207FF1, &h15E3765B, &h8B29201E
Data &h6E64C8E3, &hFCA49E0B, &h472D578C, &hB853BEC4, &hFC4D3BE8, &hAA401226
Data &h184AE1EE, &h3EFF3F30, &hBE9615FA, &h70DEA63B, &h314058F1, &h1E2136F1
Data &hD9F037D6, &hB687217C, &h9AB5F11A, &hA21E4DA0, &h9C2E8B06, &h4F591571
Data &hEE176670, &hE6F30326, &h1FC80383, &h6D62C6D1, &h46ACA2B5, &h2C31BF92
Data &h3B3D4A01, &hE1023117, &h7C392922, &h9086A414, &hF159C926, &h94EC1549
Data &h3B9B6F43, &h0B7D969A, &h48A63D65, &h074755AF, &h88AF8C95, &h572AAB7B
Data &h7CE6326B, &h4B16911D, &h902BDB6E, &h572506D1, &hC56E1E30, &h84281892
Data &hE945C4F1, &h05D1D6E3, &h0A916D76, &h12FCB618, &hCC89AE5C, &h76CB1684
Data &h1EC8FD31, &h45C04FE0, &h33CB1776, &h56F3EAC6, &h04C2BA50, &h1287A9E1
Data &hFEB1D712, &h9CCB4E8D, &h7F2C6779, &hB015C7D7, &h4920070A, &h4F56C9AE
Data &h159ED953, &h6AA8A51F, &h0B16FF08, &hB2C24D66, &h5F17F32C, &hA854480E
Data &h300B8FA8, &h1C6FBF03, &hB6F80B00, &h3A1A9328, &hDFDFFA2A, &h2346F0DD
Data &hC7E8D999, &hC6069E85, &h13FA5A9C, &hDAD1A7C5, &h43310254, &h608C78A3
Data &h4929D4A6, &h075B740F, &hB3A241E2, &h10E21E01, &h369154D1, &hCB5B3F2D
Data &hD153EA3F, &hE18F0762, &h98833EF2, &h2B0330BC, &h914E1D5E, &h67040DB9
Data &h5D501CF1, &hBE992973, &hF6E20483, &h989A13B1, &hCCE8427E, &hB68D536D
Data &hE05FCAF4, &hF9DAEE73, &h1700E0F5, &h07602350, &hB4990215, &h7589F135
Data &h554A7364, &h5720A335, &h4963BE93, &hB2D3796E, &h65741082, &h9E3DDD11
Data &h78CD83C6, &h64735F11, &h9622DEE4, &hCBCC1535, &hD1D8418A, &hA645FA91
Data &h0426B1AA, &h6E1E9407, &hC4D8D89E, &hDA618AE0, &hF55D2582, &h8506DD00
Data &hC41EA94B, &h840BCC1A, &h65386775, &h3EE356D4, &h531EBFC9, &h07752287
Data &h03988906, &h7E9D2EC4, &hB08D905A, &hCF8BD2F2, &hFAF79358, &h62734EE3
Data &h075ABF39, &h53C4D21F, &h9BACA669, &hB3E94309, &h52C1C71C, &h25853F44
Data &hEC128B6E, &h9596B321, &hE2E11178, &h58E4CE7E, &h85A0805E, &h9F485938
Data &h34A353F7, &h30283FE9, &h42BA93B5, &h288A54B6, &h38EF2D28, &hC493C875
Data &hC23D05E2, &h9BBFCA40, &hF6256AAC, &hE2B082C4, &hA3CF12DF, &hA4BE49B7
Data &h9AB1F639, &h48C34589, &h7115D805, &h06162818, &h186AC0BD, &h7E8F32D3
Data &h35187873, &h72F00819, &h899E6C32, &h02CC3673, &hE8550F63, &h482F4DA0
Data &h5CFC6029, &hDBEBAB7D, &h9337F904, &h6FB0D051, &h5A641F96, &h084ABD5A
Data &h238B494E, &h13C61E7A, &h51751217, &hD461761D, &hC4C956D5, &h18E761A3
Data &h81492570, &h7A3DD8DE, &h7461011A, &h68B51CAF, &h00D8B3B5, &h01F0FAE9
Data &h5D5FDB69, &hD86E1086, &h4D0D9917, &hDD842435, &h0C1D7753, &hAAF6CD33
Data &hC834B2BB, &h985737FA, &hDD9C92B0, &hE3E99F65, &h218E9D42, &h374BEF21
Data &hFC6CB2DA, &h6C5902E2, &h2BC3DF51, &h4C268D19, &h81600321, &hF3D7BB20
Data &h612390E0, &h9F6E3978, &h5217BCFC, &hC95A8C68, &h7775A946, &h5853B9F0
Data &h02BED278, &h734625D0, &hC9DAF931, &h310DED59, &hF70536B9, &h6974BAA2
Data &h9E57D5E7, &h82607C66, &h521561F9, &h33B6469F, &h9342F5D3, &hB061B362
Data &h60043A06, &h1D92C5B8, &h0C10AA80, &h86856587, &h2E17BAF6, &hC49529B2
Data &hCC97B773, &h7000DEE0, &hDF9869A0, &h6F491141, &h120BCD01, &h368E4575
Data &h0A45C13F, &h63960835, &h986D357E, &h3FC60B48, &h2A9B7978, &h106BB0EC
Data &h0FEA3D32, &hEB332A39, &h1CE65CA0, &hCBDAC8E6, &h53705DF7, &h69CFC5A9
Data &hC520DA87, &h65F84D0F, &hA6388267, &h91138FF6, &h3038DC1A, &hA9EC9AD3
Data &h958018D1, &h261AC590, &hEF8DCB43, &h48933920, &h45F146DB, &h73FB17E4
Data &hC5791474, &hD1FCAE3E, &h4B77F1DD, &hEF6ACA60, &h330229F5, &hEDBDA584
Data &h7C33C463, &h414D3F3C, &h7CE167B4, &h8B01258E, &h7E6C04D5, &hEC3C7C40
Data &h5B176523, &h0FF0BDBC, &h557B175F, &h925FD04A, &h47E35432, &h16C13C05
Data &hCD085063, &h181D875D, &h58F0A295, &hF02A7C54, &h0610906B, &hC6830F51
Data &h2E85AFF9, &h5FCD4296, &hB191BA53, &h96B25A4A, &h26C73866, &h316E2F3E
Data &hE1ABCBF7, &hC04AD94F, &h323C88EA, &hB87ACDB6, &h2A00EBC6, &hABC89C3F
Data &h1E60FD8B, &hF22A2FC4, &hE5FA4036, &h5A376687, &h0E8A69F0, &h8336903A
Data &h52281431, &hF6AC8517, &h56811CB8, &hBA85A04F, &h57DFC6D4, &hD49ADC30
Data &h757992E9, &hF16341E8, &h2953B4F5, &h763EE792, &h69A215E4, &h5D504630
Data &hCEB07617, &h44B55579, &h3296F6EB, &hA7C5C7DA, &h1DC4EEFC, &h0AD4E605
Data &h83C00953, &h9658CB21, &h3BCCD526, &hB5FEEDED, &h121BC065, &h0F6A2978
Data &h31D04C2A, &hF54C9FF8, &hF3D91675, &hAF6DD3AD, &h64A0E4C4, &h465C8722
Data &hA88F4329, &hABBB2B02, &h927A1037, &h250785FD, &h541D1E84, &hF7C167D3
Data &h12724C06, &h990C4ADD, &hF47EA921, &h0DD56A99, &hB36E3FA3, &hAAB18A8F
Data &hFC0E35B6, &h12F473D5, &h7AAC1E36, &h3396070E, &hB8E9CBF3, &hA2060844
Data &hD75DBBC5, &h0F05B3DC, &h6237BF25, &hD77A6711, &hEB4B4036, &hE01A053C
Data &h48C9E919, &hA0682628, &h89B8A97C, &hDE556ADE, &hFF380326, &hDF8672E5
Data &hCE951A93, &hCCBBCE21, &h98519338, &hBFD43A1C, &h8A0438FA, &h11B4AC92
Data &hE6F36AC6, &h7BA42456, &h2984E590, &h8F8F7CDC, &h81177FD4, &hACCD3D38
Data &hEA8646B6, &hE0128CA8, &h3648F6B8, &hA276DA94, &h1719D683, &h0A5C9839
Data &h6A6C0C43, &hAB00112F, &h203B8A09, &h5DEE548C, &hCD8ED8B7, &hD25ECC99
Data &h43ED6766, &h0048C003, &h0AC9993D, &hBB5B3E3D, &hE969DFE0, &hC1C3B19E
Data &h7D95D239, &hF331AD5B, &hFF14A666, &h7D0BF6EA, &hC4FED0E1, &hF1F44CE7
Data &h5FF9DEA1, &h9587739A, &h4FA4348F, &h9F38D20F, &hE061619E, &h5449A376
Data &hB198DB44, &h7D6F0B72, &hC8568EAD, &h2868B2C0, &h24BF5C6E, &h90F37286
Data &h50363A4A, &h3622D8EE, &h9CC03323, &hF8E8260A, &h1FAE8E45, &h09FE86D6
Data &h7AD71010, &h97356F0C, &hB8A22B27, &h0C360F4C, &h1100FDFD, &hB4863031
Data &h4843FF28, &h61332928, &h612F2A91, &h396B0CDC, &h0D7715F5, &hDC633490
Data &hF1B0BDB4, &h8CF1173B, &hFFE7E9D6, &h4FD69BD8, &h8CD05359, &h4C66469A
Data &h14620AEC, &hAD788931, &h84DE7195, &h98E0C265, &h32D2B106, &h6ED4AC23
Data &h3826FAC2, &h9373B8F5, &h646F6B23, &hAA60E7BE, &h16C8BE5F, &h73759D20
Data &h47026670, &h69243C29, &h3E682089, &h8288B352, &h22F840EA, &h4C7EA163
Data &hD6E96049, &hC119DFE8, &h54453675, &h2A407E26, &h8EC1A6E0, &h8D98CB1A
Data &hDCBA6193, &h89483898, &hC4062CCC, &hEC24EE4E, &h43E57B93, &hB5501332
Data &hD771A8BD, &h1AEDC153, &h93CED4AB, &hBEF96A3E, &hBDB8298E, &h41598049
Data &hB4D59C9F, &hE6D89466, &h79114CE0, &h8260E0D4, &h0F4CC905, &hE76C407A
Data &hCA00A277, &h94BEC1D4, &h53E22A1D, &hB436C0F4, &h8734497C, &h760B1A3A
Data &h95AF41D7, &h4EDDF9EA, &h8B878177, &h287DFACA, &h2B463482, &hDC3721FC
Data &h44DC4271, &hABBCDD4A, &hC3624B38, &hC2D2B523, &hD8E4353B, &h588FAD0F
Data &h1C474351, &hC0189313, &h7D5342AA, &h872BF33B, &hF10A91D3, &h9A97DA07
Data &h302BDE62, &h34A337D8, &hB1DD5D68, &h2D7A2A1E, &h887F69AF, &h79DC9BE6
Data &h55C21AB9, &h67908FF7, &h467ABD5C, &h65651540, &h804641FC, &h2A0A0C2C
Data &hE215E506, &h44403863, &h2F78B147, &h0663320A, &h4D022E15, &h386353A0
Data &h4B1D6BC0, &h36A8BB0F, &h5C7F10D8, &h150C002C, &hF97D1F5A, &h4E61A746
Data &hBD643B13, &hE58BBA1C, &h881C27F8, &h6642CE04, &hFDAA88E5, &h8D79F4B9
Data &h6C9508EF, &h1C84F2CC, &h760D56BC, &h6B88C6CA, &h8F0A0955, &hA9C575EE
Data &hAF5CFCD3, &h504C8F9F, &h01B5265A, &h09F6BB62, &hDC5412B8, &hD1DE4ADF
Data &hEBAB1467, &h818D3DF0, &h01743FDC, &hE84500E6, &h7DF70227, &hD4975127
Data &hD84B3ABE, &hA97177A4, &h3ACF0E08, &hB939C9B9, &h11F6B550, &h55429A78
Data &h4DDB8E97, &h4B9DB92B, &hEF9EDB34, &hDEF4782F, &h1A044B5B, &hE2F86E94
Data &hDD898A66, &h36F496D8, &h4B6AB424, &h66FB4C2B, &hFC82B38C, &h48504E9D
Data &h340061E8, &h277B00B1, &h824B54E6, &hB82F7CC6, &h6124A0B3, &hDB95E3AC
Data &h2A984E39, &hD8B34C96, &hC167B767, &hBDBE21C5, &h518D8675, &hEB214413
Data &hC8EC857F, &hA682DEC7, &hC58098D3, &h9D563EFE, &h23B27721, &h31FB4581
Data &h49D722CE, &h1A22D985, &h6CB4DDB5, &h4A3E363F, &hC6776CCF, &hC9C1E3A8
Data &h764CE373, &h011245B7, &h9EF1D897, &h01D35317, &h6C6903ED, &hF25EC11D
Data &h72292CCA, &hA38982FD, &hF4CB058B, &h0BF22C3D, &hF771D6D6, &h9464C90C
Data &h8B2AD5B9, &h86B8CFED, &h67AD333F, &h8A01C78F, &h83998507, &hDAA06F2E
Data &h53751C63, &h8DE71087, &hFC257653, &h38138046, &hFE265563, &h3E34F3E1
Data &hE84F16FD, &h3E144D98, &hA6911B1D, &h128D2E89, &h12A9BDDB, &hD2D3B805
Data &h5444E794, &h1D9977DE, &h6E67CF62, &hEE286005, &hA2B03C07, &hF8DD2F86
Data &h2158E2DF, &h23448468, &hC2AD8EFC, &h8870BC01, &hF36FE7C5, &h4A3D912F
Data &hDCB36453, &h345FB457, &h664C5755, &h6F8DC6AE, &h1C0B8B3B, &h099F8ADE
Data &h1F2C2D84, &h77A4FD87, &hF76F8C60, &hC0236722, &hB69B2865, &h2175911F
Data &hF84EF237, &h2B0E2270, &h2F244BB7, &h9A5B754E, &h9BFF2392, &h4D660A5D
Data &hB164C335, &hF8CA0F1E, &h2F45B5AF, &hADA0959D, &h393479FB, &hC703A4CC
Data &hE85C1CC5, &h6F578065, &hCCDF246F, &h824D54A0, &hAB9D5F9E, &h66BD0BED
Data &h7E39E131, &h3FC94137, &h24570CAC, &h413AC931, &h59ED5ED2, &hD26EAB7C
Data &h0D6C7939, &h7CFA2A57, &hD17ED066, &h943225C2, &hBCA4F646, &h803D6024
Data &h19FBFF98, &h01BEA1D2, &h919ADC39, &h448F7A83, &h5C67087A, &hD81E8061
Data &h4FF0839C, &h823F6E13, &h16F86019, &hF02A7599, &h8A26A13B, &hD5B83321
Data &hFB1AB7C7, &h22CBEA98, &hC633E6BD, &hC12472E1, &h82FD4BA4, &h4F25656B
Data &hA166891A, &hC32C1A41, &hE3DE00FF, &hAE6C5313, &h2CA095D8, &h644DC5EA
Data &h211DE8EA, &h27C288AA, &h4B857D9D, &h02612F9C, &h8C4435B4, &h8B2F3072
Data &h0814CDE3, &hFC698E51, &h1172631A, &h94F7E95F, &h50D22B93, &hB909FAF7
Data &hC13971E4, &h0D553B22, &h79AE940D, &hA01E2DE1, &h06A41465, &hA4013189
Data &h3319B1AD, &h826D40C9, &h6EB90699, &h6AE0D57F, &h1E8280EA, &h53E1E58C
Data &h948178AA, &h3DD4AC66, &h44A6F58B, &h957B9B12, &h7EEE009F, &h0FAD96C5
Data &h6761F302, &h0BC9FCC0, &h940C9050, &h23C8A760, &h50A46434, &h1DEA65D9
Data &h6682BD2E, &h09F60A21, &hF42E7EC0, &h6F7FEA3D, &h54742B1B, &h7708326F
Data &hD3818B96, &hAEA97069, &hD48A82F0, &hE98D383A, &h185C8C2F, &hD24407C7
Data &hE10B1914, &h0673E7C2, &hD87FCA78, &h3D0CB8C8, &hE97852B8, &h0896A1A1
Data &h1F8328CA, &hA559EB7C, &h68A97662, &h8885BD65, &h511A7F1C, &h354868CB
Data &hD495215D, &h69FF53FF, &h7F3AFBA2, &hEE5FDF61, &hB9371A20, &h9BAE62DD
Data &h92E35B30, &h6D433AFF, &h7949CD06, &h2D607922, &hD15CF1E1, &h2097F8D4
Data &h9DC84683, &hEDCD6F0A, &h43EEEBB8, &h97DC53F3, &h99E44102, &h484613ED
Data &h640962B8, &h107D90D2, &h3C704F98, &h1F86CC7E, &h0269C6AF, &h69F77F5D
Data &h50D87CC9, &h138045BE, &hBA85E2B9, &h66A6E3A6, &h48347B6A, &h8B3960C0
Data &h31E25C60, &hF398E887, &h80C6AB64, &h929DAB3B, &h94DDFBF9, &h84A1CE0B
Data &hE3532082, &h387E4AAA, &h6EC2AF72, &hF27DB64F, &h442FADD8, &hA598D2EE
Data &h81C07B3A, &hA504341D, &h9FB3F18B, &hED27AD09, &h36BD6E9F, &h99FEF211
Data &hFF119360, &h56600AF7, &hF3B0E069, &hE8EA6C30, &h47A94E3D, &h54228CE3
Data &hC34CC7C1, &h43E0AF69, &hAC9D1118, &h492A1B0A, &h1180D270, &hABC83542
Data &hE744E4B8, &hCFE61DD4, &h52979334, &hF11F52D9, &h76AAD0B8, &h66A17ED0
Data &h8DF61606, &h3892C67E, &hAA266F98, &h064D1F32, &h44255972, &h9114CCEB
Data &h1C72D94B, &h0865E900, &h4C9A6496, &h34A5B2EB, &h79468576, &hFC4FE0B5
Data &h65C88913, &h653DBA8F, &hE14E3F14, &h31AE05CC, &h7A4D5C5E, &hC881C9EF
Data &hC033D681, &h8F61EA84, &h07FF7709, &h4DD78201, &h197A225C, &hDB74490B
Data &h442B10DB, &h3AB435D0, &h5F7DF6FF, &h20FA6D9F, &h22C4DEF6, &h325C6B52
Data &hD8B16FF2, &h5D575EAC, &h02A1F9D9, &h90829000, &h3B24EE9C, &h1324A7A3
Data &hC3BD8F48, &h6404442B, &hC77E57B3, &h7EAD4135, &hE23684C7, &hB8F32EF7
Data &hB33D4414, &h933493D8, &h8BE2DD67, &h2768079C, &h6E0ED3EB, &h9CED00A7
Data &hA9E252B5, &hF10A80E0, &hEF39DD82, &h21AE3E5F, &hBBED45A4, &hF914848B
Data &h27D25C4B, &h7BBB359B, &h05D5B540, &hB3870CD5, &h0A83F56D, &h7A0C596D
Data &hA2AE1E46, &hDBBC477A, &hD4214046, &h09BB1886, &hAED22977, &h4ED2C08A
Data &h8EE20D85, &h3C4D04B9, &h24B2A247, &h19F9565C, &h106BCE5D, &h0EDA8CC5
Data &hEE96A873, &h1E5CDFEF, &hB99063FB, &h47061DF0, &hC707D4EA, &h394EA875
Data &hFFBA43B4, &h3B6855A9, &h85872998, &hB5EDB23B, &hD1DBA0E9, &h6635D3CB
Data &h3078AEE7, &h3B132C17, &h843B9A5D, &h3AEE7D8C, &h8052B374, &h43987D51
Data &h83535E3D, &h0A835267, &hDCE6B3EE, &h84BBFC23, &hDE70DAE3, &hA7698BE3
Data &h92E7BECE, &h33A8FFBA, &h794EB6DC, &hFC53D915, &h2BDE7204, &h0AD7D772
Data &hE1AE1CEA, &hA8FAEDC5, &h33058404, &h3FE3BACF, &h585433A4, &hACB02B08
Data &hE44F67AD, &h2940B961, &h81611E84, &h64C16367, &hAFE75A51, &hF2BF4C88
Data &h552BE967, &hFB3323A1, &hF32B3EF4, &h19B30410, &hF974ABF4, &h9F214DD9
Data &h201AC9D5, &h2FBF4B95, &h001A0C3D, &hF9B0F207, &h0FA0BC39, &h3D8A58A7
Data &h0CC09324, &hAC5F5765, &h89470D56, &h3371687F, &h0B7F074C, &h644FD2C4
Data &h5DA376DA, &h738E4F51, &hADE4EE9D, &hE704E14A, &hA7F02E33, &hB06FE01A
Data &h4470D672, &hF0F42344, &h36DF4E76, &h6A5A82E0, &h543CA1ED, &hFB5E6CE3
Data &h45E4B914, &hFE7FFB4D, &hF7E43FF6, &h201E6660, &h169F7FD0, &h8D5368B9
Data &hAF389B97, &h516BD901, &h604192CE, &hBED4DC9B, &h8FFCFC83, &h049B976E
Data &hA6F629B6, &h8894829C, &h18C05DE1, &h46797D26, &h90C54CAE, &h2C6A3A5D
Data &h8612AAB3, &h6DA77946, &hD857E54E, &h5D2DC0F9, &h42FB6681, &h86CD5DB5
Data &h67A62ABA, &h4415FE46, &h0C7479EF, &hE9574FAE, &h33CFDA53, &h335ACF3D
Data &hA5E79EF1, &hB7833E9E, &h3905422A, &h0E948B11, &h40F4195A, &hF9079146
Data &h28E84AF7, &h5F1908AF, &h1D3AF84D, &h9116CDD0, &hAE58D459, &hA36E33A4
Data &h0AD6C1E1, &hA58A9B69, &h2B4C47FE, &h2D6EAEC8, &h3D4FBA7D, &h9539277B
Data &h5E3352BB, &h40967F2A, &hC052352E, &hBC98C83D, &h761E04B9, &hB641BCC7
Data &hFDC7A4CC, &hFBF9281A, &hC1D51A00, &h29256435, &h422EA705, &hD290044C
Data &h4B1DBF40, &hBC67A3F5, &hAA6C1120, &hE44E9209, &h35598D18, &h475F76B3
Data &h0CF22639, &h2D8E58A6, &hA6AF90A3, &hC000A94F, &hCA32F40F, &h978704D3
Data &h06D58D91, &h776609A9, &h52951EB6, &h46567957, &hD501FE46, &hE941D714
Data &h695C480A, &h7FC9DA39, &hD4F50E94, &hC9ED1779, &hABC1A7B3, &h8F4445EB
Data &hCA481300, &h2EBC7000, &h05651046, &h4472AE7B, &h47676E44, &h27857933
Data &hEFDE2E6A, &hCF907C19, &h528021DC, &h5EAD0B19, &hF0C8504B, &h5AFC5050
Data &h7982F132, &h85A3EA84, &h0D4D0260, &hC02F65AC, &h5516A762, &h31208E0F
Data &hEAF18DF9, &hE6278308, &h64F0C8A0, &hD8803B0D, &h82FEF527, &hA023C453
Data &hFC292003, &hB2B0FDE0, &hA5BE4CB8, &h800D7D69, &hF94D2CED, &hF22AF4B0
Data &hE58B144B, &h3B48B0E7, &hDAB40825, &h8D562676, &h8F9731FB, &h8629F11A
Data &hA269FBF9, &hB7E2FD32, &h8E053795, &h9F609959, &hDE4CFA11, &hA86D2658
Data &h71B4098D, &h4091055D, &hB911F121, &h32B50986, &h162F6938, &hF7BA8ABA
Data &hDCBBE1F4, &h6F2286FC, &h1FA4D351, &hFC89233C, &h5790602A, &hC6CFC2A4
Data &h9EACC942, &h208E89B2, &h5C35A727, &hEB8BCBE3, &hBD3EA989, &h0214F25F
Data &hB643897F, &h94AC15DD, &h78CC86FA, &h24ABF6DC, &hF225B1AF, &hBD2C2B71
Data &hAD742417, &h40A5F947, &h77D14AD2, &h03DE5CE6, &hCBD9EED1, &h8C639537
Data &hE0B4CADB, &hDC468E76, &hD8E46353, &h87A084CD, &hAE3E644E, &hBB667080
Data &hA347EB5F, &hA214D507, &h2EA85C92, &h2F1E0FAF, &hBDFDDE9C, &hC7B0486B
Data &hA22187AE, &h98CE500B, &hCF72C717, &h7E55B3EE, &h814BD736, &h4B083EAA
Data &hD805F415, &h2ACE02A3, &h6B6AA1DE, &hC300B254, &h6B0B949A, &h84A938D2
Data &h5FB28497, &h79A5B00B, &h9739849A, &h90EB189C, &h21259256, &h6D0B9F6B
Data &hB41AC9E6, &hC0D28A16, &hD2BEBCA3, &hCD14FB69, &h1A7D6AC6, &hE7D05A98
Data &h2BCAE7B8, &h45EBF266, &h4ADD4992, &h8CBD4928, &h695D0BA5, &h46B39659
Data &h7BBEC5A6, &h098A34EA, &h6AC90FDE, &hDE09A598, &hCDC69D3B, &h3724F9C6
Data &h5B2AC24B, &h68D372A3, &hE6CB2972, &hC632E061, &h4F6A417D, &hDB20023F
Data &h1F4D3A89, &hC637AE9E, &h854DF07F, &h9D6EEAC1, &h6DFE0B0F, &h50047953
Data &h6E66BF31, &h3D177021, &h50D0D44D, &hE518A52D, &h71F8253A, &hAE1F080F
Data &h218503D0, &h3B241DBC, &hB357CD28, &h0C693585, &hF2DF615D, &h2A95FA86
Data &h834A8EA3, &hF7950155, &h8E2F1783, &hB3B0A09B, &h7D4DD7DA, &h2138E9F2
Data &h37A7363C, &h929E3876, &hAE5CB91D, &h6D288314, &hF56E3519, &h9C046426
Data &h6A80C8D6, &hF9D48E89, &hFB066483, &hA51ADB52, &h7568BC14, &h29B88430
Data &h12AEFDD2, &hB19C1F62, &h6B380442, &hB6A7BEEE, &h2472B9F7, &hBD1C554D
Data &h68737E95, &h91DBCA19, &h7A58A4AF, &hCA8592AA, &h84E51FA9, &h111BFB06
Data &h7C69441C, &h69DD2EA3, &h798021A0, &hA6493390, &h96BFDC51, &hFFE3E380
Data &h111F0815, &hD8EBF0B7, &h2053D1CF, &hC1BCDFCE, &hEEFC0B37, &h9BEEF683
Data &h02BC4989, &h33C2A6AA, &hB86C1C06, &hC15D45E9, &h16D5D88D, &hC52EADFA
Data &hAEA2DA58, &hB65C99D7, &h8464851B, &h7C337688, &hC096A599, &hE9805953
Data &hD55CE74F, &h9A5BC285, &h146B20AB, &hEFD7D62C, &h7B18B87C, &h0C8B705B
Data &hC0AFEBBE, &h626CDD5E, &h9748C3EF, &h073E63D6, &hF9FDE12B, &h65C91B72
Data &h51907D7D, &h5C31C4D3, &h42D5D04D, &hA1E8E855, &h8B873302, &hC43D6E85
Data &h5AF378ED, &h12F0EA54, &h6C10B34A, &h106EC590, &h47EBC26C, &hB13F728F
Data &hF5C5D46E, &h2AE6D382, &h0350DAE6, &h4F3A127F, &h4B14D33C, &h79A04512
Data &hC9F6F236, &h7CD92035, &h8BE0C2E4, &h45316727, &h33EEBE0C, &hAE1A8437
Data &hC3BA1C5A, &hE1249301, &hB764FF85, &h7F1F88D1, &h2BF80B3D, &h8F383DFC
Data &hCBB1F6D3, &hE1C6B7E3, &hABEAADA6, &h2C2D6AC0, &hF0B1C0FC, &hA17548E3
Data &hB3F9334A, &hAFC6F6C1, &hF4E0F397, &hF1A577B9, &h53D33F9B, &h05E1B6CD
Data &h146EF620, &hC97173C8, &h3B885E71, &h08BF2ED5, &hF78C86B1, &h172C548B
Data &h5C16FEC9, &h92AD700F, &h5FEAA01D, &h98B6DFFC, &h6DA2C170, &hFBE75DD6
Data &hB424CA1B, &h248D6AB3, &hC789D1F4, &hDF38ABED, &h0347CFE2, &hE3DB76BC
Data &h27E6CB6F, &h1DBCD7DA, &h74044C33, &h4DD0BCB6, &h04995EAA, &h775BD919
Data &hCC034E1D, &hB0F6E34D, &h5EAD5F84, &hC9A559E8, &h9F78C7C0, &hDF2E0ABB
Data &hC7BB5186, &hD4AFA684, &hFCD6B9A1, &hAFAC0844, &h45996461, &hB6D1784F
Data &h55FC4728, &h31C9A66C, &h33F1CD2D, &h0F062D77, &hEE1F7E97, &h3D69693C
Data &h69C0DDF6, &hDAC65A21, &hC9E3416B, &h01302F12, &h33A3F2EF, &h7726A99C
Data &h98A5ECB4, &hCE8D9810, &h8A2B27B7, &h6DD1E324, &h22F4C810, &h67A86648
Data &h93D41930, &hC9CD2CD3, &h25FB3160, &hE3E54FC8, &hA5185ED3, &hA37FCC6C
Data &h5CB9D905, &hFFA05BAE, &hF8363D28, &h26DECCB1, &hEC52BCE5, &hE44FBF01
Data &hD04CDF59, &hF35DBB96, &hDC4DEB47, &hA9F1BA23, &hB96E4145, &hE023FE4D
Data &hCDE4D53A, &hDE04FE10, &h55E47C8A, &h3CB421E8, &hCE022E85, &hF973A2BE
Data &h10ED785A, &hD65EDFDB, &hF2F58BAD, &h3523A982, &h5442D144, &h32C4D3F6
Data &h7315258E, &hEE829847, &hD096FDB8, &hC0A82CC2, &h1AB0C8AC, &h6F75CB1E
Data &h1D866B25, &h8A5783A3, &hF68AF703, &h8A6CB0BE, &h703A9CFB, &h685A23C7
Data &h0E6528F0, &hAA894F89, &hE007E37F, &h6C439AA6, &h04ECF9E0, &h5D7B82A8
Data &h75880C99, &h09145B09, &h10F7302B, &hDE72FBFC, &h5F7007FC, &h231733A7
Data &h17A978B2, &h34EB6F54, &h0FCB5009, &hEB857A53, &h3D1F14AD, &h7F73E534
Data &hF14D8723, &hE5A137FB, &h4A3B8138, &hEB0EAE2B, &h6877B9BA, &hC0C50642
Data &h49D57157, &h07FCCD14, &h7CD057D1, &h007D6F55, &hB3670ACF, &h466CF42A
Data &hB5CC6590, &hE62201D5, &h8907CEFE, &hE6FAB790, &h962306DB, &hCFF37F38
Data &h798B2A79, &h3085D95C, &h3A1A0FFE, &h7C0D8683, &h5CB18BCA, &hBE81D6D2
Data &h4835734D, &hDA4D3708, &h6E63320B, &h790D1DBA, &hA01D89BC, &h936921AB
Data &h5E55472E, &h48E3A98C, &h0E156195, &h57FD71F5, &hE5A27129, &hF1567AA3
Data &h42A97D66, &h66E1A373, &h5E51A798, &h13E3D723, &hC6390598, &h2AE7603E
Data &h80FB9461, &h0EFF4769, &hFE5DB530, &h1AB216B2, &hF8C780C2, &h1E604317
Data &h35243FE3, &h0709B67A, &h7209703C, &h9133724F, &hD1201B4C, &h6C9FF324
Data &h754E43AC, &hC3DC7226, &hADF7041C, &hA570BE16, &hBDE82649, &h3BE2D6C0
Data &h5A8E1550, &hAFC5F71E, &hE2D7B560, &h0A6CEE24, &h2248E660, &hB6ACB8A8
Data &hE1F19808, &hF6DCFCB6, &h3F78F47F, &h7953BFA5, &hC35A6596, &hD8925BF0
Data &hAD63A32E, &h2C7C3228, &h06191CB1, &h529C1DD4, &hB67F3CC1, &hF0D3FAAD
Data &h467FD774, &h4782969D, &hE0F81383, &h5C3AEC98, &hAE324704, &h2A82C782
Data &h888C3113, &hB295F188, &h66607C53, &hE9B5B992, &h52E9CF71, &hAD8D3493
Data &h5E492EA7, &h66A0D7E6, &h67487DCB, &h73299FF1, &hA4657E56, &hCFA045D8
Data &hA80F6C1F, &h280DAB38, &h8998B595, &h5D10D057, &h941BFA36, &hC71927EC
Data &h1DB3FDEA, &h16CB5A07, &h057EEB34, &h70511C82, &h5F95E03A, &h444F0736
Data &h5B1FF425, &h5B748771, &h23B91340, &h203F11CA, &h9E5552AB, &hC4F6AFE6
Data &hAA076BF0, &h481B56D8, &h0593B1AD, &h48ADC1C6, &hDC4F6025, &hBA0D982D
Data &h4505ECF1, &hDC31AAFE, &hC973E30D, &h0BB982B5, &h377F049C, &h98EE1FF7
Data &h27B477E3, &h14FE33CD, &h1976DC31, &h3184F3DB, &hEEF45642, &h38EFEAD0
Data &h6E3F2429, &h71326C05, &hFBDB0D94, &hA9F68A41, &h44C2D3B6, &hC7A2E557
Data &h9E063450, &hC273B0DA, &h2520CFE6, &hDB0769C9, &h334D7288, &h2FF9E92A
Data &h442D13E3, &hA4CBF28E, &hDA481535, &hF77EBBCB, &hE8E47112, &hDB83DC84
Data &hB50EB78D, &h5100563B, &h573C4082, &h0CE78B1A, &hFC4E5CF7, &hB97FE3F2
Data &h83DFB21D, &hD04AF68F, &h9A9BF076, &hBE8A818E, &hBDC2B865, &hCF4AEC41
Data &h4BB1DC8B, &hC83BBD81, &hA81186FC, &h43D79FCA, &hE94D94EB, &hD6AB3313
Data &hF85284E8, &h0F113BDF, &h10C2445A, &hA3676864, &hB4BF4F18, &h2212CB13
Data &h15D15D26, &h4227FE42, &hD484F769, &hCEE59637, &hA1C6033A, &hD4B4444A
Data &h5389DE25, &h1B5527AC, &h0F2FA503, &hB2F0AFDB, &h3092FB85, &h11B66B15
Data &hD6758E92, &hB2C092FC, &hE641C057, &h634E44D6, &h0B01B82D, &hEABCB4B4
Data &hCB8AE3D2, &h25C14EDC, &h09F748BC, &h5876BC66, &hE34DBABB, &hD7B76BB9
Data &h614A41A9, &h0A28B31E, &h1B37E650, &h4EFC8A6F, &h54E0B965, &h27F09428
Data &hAB951E0F, &hEFBC7077, &h0E9CA843, &h890B0DA8, &hEF6212BA, &hCDBE745D
Data &h7D706967, &hF544AD1F, &hEEB32C2F, &hAA26D889, &h390C5B70, &h6EA3AC10
Data &hF3E0E3B3, &h60CF0BCC, &hDB340086, &h1B4896E4, &h50999579, &h020A046B
Data &h0D906771, &hCA1DB7AB, &h27A468E5, &h6F7861EC, &h3ED46E8B, &hDCF2979A
Data &h3DD8BF21, &h738574D7, &h86711B0E, &h7A47FE72, &h2C4681C8, &hC6F3441F
Data &hC6F71275, &hC3BB2275, &h07E36FE0, &h82A80FD2, &h3A9F558E, &h62021420
Data &h1665F1D0, &h44D78227, &h604B6A31, &h6B24C25B, &h2E15BD11, &h4A6F8D94
Data &h099DBC63, &hB2742DD7, &h460945E3, &h44D7FC0D, &h46A6DAA7, &h025CA091
Data &h4F409182, &h5E8919C6, &h004E3D5B, &h30F97BD3, &hCB49284B, &hF6296D57
Data &h9DFDB354, &h8849C0F2, &hBD735A91, &h55711C8E, &hAC9D7EDA, &hB689FD9D
Data &hBAFBD1EC, &hCE7C6234, &hAFAEDEF1, &h4102D31E, &hF023DCE0, &h2165EA20
Data &hC6F16126, &hC705FC74, &hB5CE1342, &hE47D6A75, &h1755E5D8, &h9427F614
Data &hC9371F54, &h2E8A42F8, &hE2D2F098, &h8F4C3F87, &h76F21ED2, &hA381629B
Data &hDF367CAE, &h7F0170E3, &h7A97F3D0, &hCD503B69, &h96B999FC, &hCFAE150A
Data &h11177ACB, &h7FAC4720, &h443FD615, &h2A436408, &h294F9777, &hEE3AB637
Data &h33E912B4, &h0AA89473, &hD50D0741, &h353DDD7C, &hA7F60A48, &h086B6C56
Data &h7930B7E3, &h38034C96, &h870D478A, &hC775B872, &hFD6D645E, &hCDB9E1DA
Data &hDAA315C5, &hEE6BE4B0, &hE94D3363, &hC2F61149, &h753EE997, &hCE53FD8E
Data &h31E2FB73, &hAA0E15ED, &h439A011F, &hA299FA9F, &h347CDD0C, &h396B3CE8
Data &hB2126BDD, &h32DCDF6F, &h3379339E, &h8E86944E, &hF2B9B3BC, &h0DAA55ED
Data &h6F7A83B8, &h4166EB07, &h3CFE01B0, &h45CEF23B, &hA6D85E69, &hA2AEF91B
Data &h45547DCF, &hA7E18634, &h2D051B9D, &h1B949CBA, &hBD1563BA, &h7E520912
Data &hDF518F83, &hD50BCEE6, &h7CBA8123, &h213AF49A, &h1472D0C2, &h301320BB
Data &h0F9A9858, &h2C5E159C, &h7E2B96D2, &h7C54A084, &hB0D53DDC, &h05EF27E7
Data &hB74A4CFE, &h232CDC76, &h9D081CA5, &h242C9394, &h3B11CADE, &h087C5F5E
Data &h842FABB6, &h18D3AEA3, &h246CF38D, &h9558AA31, &h78DD6253, &h59BA54B8
Data &h56B44321, &hD37F1DF6, &h02768E78, &hF6F35099, &hFDA51895, &h069CB8BE
Data &h897A99CE, &h022A619B, &h7F744F16, &hFA84810D, &hED0BCC0C, &hCAF7A4C9
Data &hBE05F94A, &hB7F44AE9, &h1654EA2D, &h1A0C150E, &hD08C394C, &h745E78F5
Data &h0519F3E2, &hB8A85241, &hA8C9A36B, &h139653C0, &hC3C4746B, &h7E941EE3
Data &h4E403ADF, &h52D80C00, &h96C840FE, &h7F9F6029, &h68D3C244, &hCA7CED72
Data &hC6004C29, &h5E187EDC, &hB0EAFF26, &h065BC9B3, &h8F738E38, &hD7E747AD
Data &h609EFC57, &h2E84D5C8, &h62D51859, &h63109815, &hDC2D59CB, &hD1F2EAF8
Data &hF55C91AA, &hDA18406D, &h8B64842A, &hEB076DA3, &h1AC7C80D, &h7CDE4BCF
Data &h8217694B, &h1D5FE7D9, &h2C8DB29F, &hD4A35AB1, &hB6BBD918, &h0F5BCCD4
Data &h5A61D658, &h809121BB, &h696AE060, &hC1AE53FD, &h961350C6, &h5990B403
Data &h0F87C17B, &hAC715DF3, &h23C86927, &hC5785639, &hC3B02523, &hD5206358
Data &h565F7097, &h6A9FCBB7, &h813953F9, &hC0E574BF, &h6B748AA0, &hA3582095
Data &h3C8B7597, &h8C1F9F81, &h351A857E, &hFB5E72B2, &h87B6E784, &h6AEBFC50
Data &hC16B110F, &h18D2813B, &hE6C8F3C2, &hCE2056AD, &hFB8F652F, &hC9D538E6
Data &hB3793C97, &h4EF253C2, &hD9D02BA6, &h34FC0194, &hC43EE3E8, &h4362F36A
Data &hBF0B4F25, &h480D0A47, &hE6FFD66A, &h152B1115, &h175D346F, &hA8F6DB57
Data &hE3FBE8CA, &h0CDE071F, &h8F619797, &h9DB2DF25, &hB480F7D6, &hC4458748
Data &h807D638C, &h31B9CD9F, &hEA5A597E, &h7C4A2A2D, &h28F29D8C, &h15CF005C
Data &h523F15EC, &hC580F8F7, &h60FF6C2F, &hB3E592F5, &h6314CD71, &h8F1D2921
Data &h74B9F32A, &hB2436290, &hC2821D15, &h4F04F1EB, &h61570BEF, &h7D36C0CB
Data &h67A39CE9, &hE01A3162, &h0D3EF144, &h998FEDCB, &h3AE1AF7C, &hEA9BEB6F
Data &h794B3C88, &h633AE96F, &h70EC4E25, &h4F97CDE3, &hD962785D, &h5B2A0A3A
Data &hADA27056, &hEF4519BC, &h4A3E5D75, &h2F570BD5, &h355227FB, &hCAB4EA0E
Data &h3160423D, &h8C043DF2, &h1D9AC769, &h8565455E, &h46E50C8C, &h8208DCC1
Data &hDCCB31DF, &h8F9F2785, &h22F7C24C, &h7170083E, &h84C6A2D6, &h9098CD31
Data &h307FABB5, &hF108A7FA, &h6CC6F0F1, &hCE0C0124, &h011650D8, &h1622DEFC
Data &h89A81582, &hE9DD4671, &hCB9B8232, &h1AF31963, &h91013DA7, &h0E6D2C77
Data &h073B82DA, &h2C01E1A9, &hE7BCF0AB, &h9BA0E714, &h40328593, &hCA5A0C54
Data &hFEED728B, &h9D13F1F2, &h65C6B542, &hA01F63CC, &h60A72F89, &h26F8F463
Data &h99D93DDD, &h36D00610, &h792695AE, &h47E52696, &h897D726C, &h0C03F00B
Data &hAA2B8DAB, &h5E3D4F6C, &h4A41E2FC, &hE6A6BD67, &h66A8A2F9, &hBEF2CE3A
Data &hABE0EEED, &h74D2B882, &h777A01E8, &h01475429, &h1E03FAB0, &hDBB110EE
Data &h7613B15D, &h2FF30975, &h8D35B6A7, &hC416953B, &h490B5550, &h61542E68
Data &hC49D1D93, &hD8E2BBE6, &hA6FDFF96, &h669F52A2, &h1DB126FA, &hBEAB9006
Data &hA3D4BA5C, &hA4EA9C8B, &h811B75B3, &h650D0B3A, &h5DED48CA, &h79A523FD
Data &hBCD9B49E, &h4C7F35D2, &hFDC06E04, &h601B53A8, &h5CA70E68, &hE6712756
Data &hDA07796A, &hD5F4CB47, &h1E323E16, &hB4CE1267, &h292C1C06, &h3D2CD43F
Data &h8B975030, &hF6B90566, &h803097B5, &h3323A58B, &hC55446AD, &h8F36F156
Data &hE66CAA2D, &h182CB5E9, &hE266011A, &h6D755EF0, &hACCF2D7B, &h39A23C36
Data &h3009B99A, &hDB5831C7, &h784264F5, &h7D9DF4DE, &h264DC3A5, &h29F38962
Data &hEB0CA2F0, &h245A38C3, &h097495A5, &h8CF052A1, &hE6AA34BC, &h7D6077CF
Data &h47CFF4DD, &h741AB116, &hEB4D4327, &h20C02E09, &hE2712DED, &h17C2EFBF
Data &h492552D2, &h1792A9EF, &h72F2A0C9, &h5E45E1ED, &hF9D71110, &hFA8A32AF
Data &h5FCF9467, &h26A47B06, &h41BEA675, &h266ECC82, &h862714A5, &hCB091714
Data &h2189A03E, &hB1D0BC68, &h2B40985E, &h556EE01D, &hDCE5B432, &h88987B44
Data &h3F2328A9, &hF56C28DC, &h486F813D, &hAB05EA5E, &h4E1FC0E1, &hEBDE7B30
Data &h61E2E23B, &h0F1FA159, &h29FB3F0E, &hC452EAF6, &h1A58C718, &h21689B81
Data &h96037784, &h84510824, &h046650FB, &hF9E4BE54, &h60741884, &hC7C37B9C
Data &hEAB3175F, &h529C6F61, &h1AD5652D, &h7AE1DCB8, &h29063C5B, &hDF81B53C
Data &h44DBF298, &h0C064DEE, &hCCEABA00, &h7E11BDD7, &hA6DD25B1, &h20A8E38E
Data &h257E0795, &hBBF91AFE, &hFCC281E5, &hF15063FD, &hDA3D4E82, &hED5FDDA2
Data &h085B3B84, &h5C413CC1, &hA6C174B7, &h86315FE5, &hEA233560, &hC9CD4BA6
Data &hA106A3FC, &h52F06EF8, &hDEC606EA, &hF8D5E12E, &hC80F501F, &h89E8C6F3
Data &h728E23CC, &h7A3FB16E, &h8804EC94, &h7357ED80, &hE8A28706, &h514BB3A9
Data &hF378F399, &h7B2087C1, &h2B645299, &h2861E3B8, &hEDC3C005, &hA7F95853
Data &h66E2B4E0, &h5FFE534B, &hEBD9EC12, &h89E5EC38, &h564402F5, &h7919FC8D
Data &h0A63ED6E, &h928495A2, &h7D3C8C37, &h57F0EFFE, &h108633F8, &h954DD74F
Data &h9B62633C, &hF81B4D9D, &h6F3D78E4, &h047F8DFA, &hE2224B57, &h47294543
Data &h0E561698, &hAE44DE5A, &hFED9B396, &h2C924286, &hAB40B351, &hE1810197
Data &h04D1CF6C, &h450BF944, &hD92EFFBE, &h3544AEE0, &h33FA6BF7, &hD60A1ACB
Data &hA5588123, &h1543543A, &hC8F3D329, &hB9CE792D, &h17E8B0F2, &h0D31BA81
Data &hCF49EFD3, &h301E5FDA, &h3995781D, &h56B61889, &h76BEDDAB, &hF14F3EC1
Data &hE101C5F7, &h57CA1509, &h9C1BB6C6, &h1F8574E5, &h91CF8AFF, &hEB54D3AC
Data &hFD2E0D41, &hD438E2B9, &h4007A668, &h6992B886, &hB6773494, &h8A656787
Data &hB9BB67D2, &h07160CFA, &hC28E86D9, &h38B97220, &h223D0161, &hC9D5B013
Data &hE42F122B, &hB1814AE7, &hC8E17CB3, &hF10C2080, &h0C87BB13, &h125001C3
Data &h86849817, &hA386DC39, &hC05ACF22, &h161AE39E, &h8C9B60F6, &hD0AAFD1E
Data &h9F342BBF, &h62A7AE58, &hFC0F7ED2, &hAA1D30E1, &hAA0D189E, &h9E3992F5
Data &h6C87F30C, &h69B94B4B, &h9AAC30CD, &h995ED9B1, &h79275F72, &h35F85D43
Data &h99B8A934, &hC31F7FB1, &h70FFAAC4, &h389BCB49, &h8BD6468F, &h809D8B1B
Data &h7749EFAA, &h5FFB0D8C, &hEF035633, &h829EC603, &h5899F63C, &hE8B9E59D
Data &h4B89033E, &h5C2C286F, &h79E502C0, &h5222AAD1, &hBF6C2470, &hC94BFCB2
Data &h70AD35B2, &h87E6CA1B, &hB9D420EA, &hDE5F8C5E, &h6BF894A7, &h421FACE2
Data &hD20A613F, &h44C98586, &h8A500482, &h899EE355, &h7CC4387E, &h858D23CB
Data &hE981CA92, &h571F827E, &hE87DF7E6, &h1D9FE8A3, &h7480AFE5, &hAB8A33AF
Data &hBFF6633A, &h2AE53D02, &hA56A2D33, &h1FB537E6, &h2165828B, &hF3C01C64
Data &h945F3BC9, &hAB38D0B3, &h614A0D8B, &hF42518CC, &h1CE35CB0, &h1089B464
Data &h42051792, &h2DEEEDE7, &h600D318C, &hEA230DAA, &hC4110B9B, &h0343981F
Data &hEFB4EC7C, &hD6D03997, &hDA9CB6EE, &h9C1948C2, &hCDF14D5E, &hB7386929
Data &h065C98E4, &h0ED458EE, &h51BB9C50, &hD130694F, &hAD60FC98, &h50CDD580
Data &h7AA7A406, &hC2C5D24D, &h0D1C4E6F, &hC1AC1002, &h40ADAE8F, &h98CB6EA6
Data &h4EDBB113, &h1AA03709, &hE8E1C871, &hE446F5EF, &h12BCD012, &hE95E80A0
Data &h5AFE8BDC, &h53A1D9CF, &h12D43180, &h094FBEA8, &h1285D57A, &hDE1695E1
Data &h4FFBC007, &h238562F3, &h9665D4E8, &h1C394923, &h94C10C93, &h4EC9E43D
Data &h6C104CE7, &h14B96218, &hC9ED6B85, &h914C5C9A, &hC20190CE, &hFC286E32
Data &h867F94FF, &hA517FB1A, &h2444D797, &h09315DD8, &h23B52FE8, &hA6ADDC20
Data &h8C0BD649, &hAB18ACB0, &h67613CAE, &hE9C7A449, &h95EA2557, &hDA494D90
Data &h2ECBA0CD, &hACB6CC05, &h26C20662, &h93BEC735, &h3C243690, &h2B6A6119
Data &hED56A269, &hF21A5D19, &h05C062CC, &h649448D1, &h16CA5E2F, &h0B5B9E71
Data &h8CC85D1A, &hDB08C816, &hD35D7DCC, &hF3F72DDF, &h37EE7B2F, &h2D8C0E2C
Data &h46E26BAB, &h0443E713, &h83D64211, &h13A38A11, &hE131D173, &hB1B02458
Data &hB288EA46, &hFE3ABF25, &hE23F9A37, &h6A8A3D98, &hF64C4EDC, &h9EA35DCC
Data &h8BB2F0E7, &h09805BFE, &h66829624, &h59C81B1D, &h4DE19FFA, &h82E88A48
Data &h0F7B824D, &hDC33DD1C, &h58B9C392, &hE914F562, &h5A636A77, &h6161E001
Data &hE6E5F666, &hC24BE7DE, &h527E749C, &hA448D6DC, &h1CF85419, &h149BBC74
Data &hF4B6F2B8, &h2784CEC5, &hD70F6181, &h50748C8E, &h552FFA7E, &hF5731C27
Data &h2B095AC1, &h579A8483, &hA7627DDA, &hF7EED352, &hD8084728, &h0ECCB93C
Data &h999F9761, &h833AD387, &hF08E2662, &hB3473978, &h012CE396, &hB93F6BE6
Data &h0C1D14DB, &h2C9F6E3B, &h26D2957F, &h6E28A36C, &hDEAFC24B, &hAEFB3EBB
Data &hBB52D317, &h0FDB5D8B, &h754446FD, &h46C3594B, &hE87B1950, &hB18B40AC
Data &hC5B4712C, &h2BE94A03, &h7EC1C83D, &hA909AC5F, &h65BDC4CA, &h0F21A106
Data &hF500C3B2, &h871F0B3D, &h5E1919D5, &hF0DEEE24, &hEB91C3A6, &h114887FE
Data &h71E2FCD6, &hEA9E362D, &h57CCA502, &h5E634150, &h54C51EA2, &h3435E119
Data &hAB1CB53B, &h6AF13080, &hB5669DDF, &hE6E6FEA0, &hC5C62C8F, &hC4341DFB
Data &h0D028F1A, &h4BF97625, &h5E71FCAD, &h1993FE83, &h2F862691, &hFC17A451
Data &h35D81D5D, &hECFB3700, &hDA7BA454, &h4078C668, &h59E1929C, &h24D0AD1F
Data &hCBF70F06, &hE5F4B4CA, &h051B064C, &h6D352EEB, &h1C6EA3DA, &h84F5A379
Data &h4F9E3715, &h8FBF4A2A, &h0DD402B8, &h8FAAC22C, &hF64D0897, &hD45409FD
Data &h92921B29, &h5A576F8E, &h016001B9, &h6DEFC381, &h7C3ECC87, &h8D42ADD0
Data &h149E29B0, &h537A36A2, &h3F4B2F41, &hC6AAC365, &h03426604, &h9F4EAAF0
Data &h2874FA97, &h793C4F76, &h99EBD4FF, &h24AFCCF6, &h129656D4, &hA5883018
Data &h7B8C41F9, &h031F159C, &h76E8382C, &h8E2E164D, &hB006ABB2, &h445A048B
Data &h2130116D, &hD92A714A, &hCE179167, &hFFF06119, &hC45C5814, &h1ABFDF1D
Data &hC16CE3BF, &hEA19907C, &h2DD9B0FE, &h3D0A8DDA, &h9A6C7088, &hBA3793F2
Data &h310B4FCD, &hC17C7A4C, &h3D4F71B0, &h703D47F4, &hC0F29475, &h28F68009
Data &h73A8A694, &h43155E1E, &h5B7FD2A5, &h5E878BFC, &h459F94E4, &h26057833
Data &hB6C2DDBF, &h50840CBD, &h8C697659, &hED58DA54, &h27ECFCDD, &h4C2A8F71
Data &hC6E7C151, &h9268C3A1, &h6EEEE4C0, &hABE140CF, &hEFC39301, &h7EF7952B
Data &h54729383, &h6DB765C7, &h9C1C05CE, &hB099ED24, &h62D521AB, &h6CB4CCEA
Data &hCECE8044, &h21746D9C, &h54204C3C, &hBF0B4B55, &h822D257E, &hCD2B4DF3
Data &h55F597F4, &h4DBDF8F3, &h08ABCCB4, &h783EA46F, &h0607AC81, &h9F593663
Data &h9E837214, &h45B4A4B5, &h7820FFFA, &h968AC809, &hE1BEABD0, &h985E3954
Data &hBCC926A9, &h135E1855, &h77FACECB, &h4DE74487, &hB1551F62, &hE5879412
Data &h0579EB9A, &hC7E9F697, &hEE4EE775, &hA08A7592, &hBE113889, &hBB7E68A8
Data &hB45A974C, &hB1A5BB6D, &h7A401178, &h69BFEAAA, &h8D72943C, &h24A9E165
Data &hBF4407D5, &hB38BD623, &h6874DB32, &hD44F6BB6, &h74FD0060, &h4AF05123
Data &hE41D1A0E, &h68EB50CB, &hCCFD50AA, &hDF31B221, &hDE5B8DA4, &h5EFB72B4
Data &hE8B6EA0A, &h10C00AB4, &h18C0BAD8, &h829F4081, &h2D611D15, &hAF59B1DB
Data &h7BDF8CE3, &hE51C6BFA, &h6A0C055F, &h97FB81D2, &h1C21B7FB, &h5EA9110F
Data &h0619D0B7, &h4F57908F, &h1BA9E904, &hCFF91F23, &h1F924B5E, &hB5B348FC
Data &hA5B97964, &hDCA6B412, &h033F4AB6, &h4B2A4589, &hD45BB491, &hBB64E5A8
Data &h52AFF185, &h17DC0AA4, &h8B8248A7, &hE801B9B8, &hC1C6EE76, &hA524A520
Data &h636D41D4, &h04BDB736, &hAC62930A, &h8AF89ECD, &h62C5128B, &h92095DDD
Data &hF4330937, &h4194ADFE, &hB24B3CA4, &h89BE416F, &h05B9B080, &h9BE98018
Data &hE25A83A4, &hF6B439B1, &h9025A56F, &hCA05E2F7, &h0D734857, &hED039591
Data &h00B34058, &h5CA71D50, &h2BF2880B, &h664EBCF6, &hB07D7971, &h2B3B5370
Data &hEE9FC4DA, &hCE166646, &h8C438D61, &hEBDA3768, &h3FCBC71E, &h08BACA0C
Data &hA76CB608, &h6384BDE1, &h37494BA1, &h9E6F8A53, &h07043633, &h044322F5
Data &h83D541AC, &h6904E633, &hE2D2F769, &hBDDCB67F, &hA176DAF8, &h1584FEEA
Data &h933368F9, &hBC45C7E3, &h0D61E084, &h1CED2B07, &hF716146A, &h56A32D81
Data &h74AACC56, &h616AEFEC, &hE2EB6C3C, &hD0CEB7EE, &h9902ED42, &h9D29D114
Data &h85F7080B, &h212913AA, &hA66E86DC, &h19908B30, &hA4DE99B4, &h2EB1BBDE
Data &h387F240D, &hDC93449D, &hE414D36F, &h1FCC0273, &h054B1CAE, &h10DBE4C6
Data &hA3C76089, &h944EFE80, &h661AAED8, &h174A12D2, &h90087CA8, &hCEB8A2A9
Data &h1294E605, &hDE50BCB4, &h7A499CB1, &h8C963D81, &h677AF8B1, &h9947C505
Data &h69E616C4, &hC3CF133E, &hAFA051F9, &h07772255, &hE578B35B, &h42E8A1BA
Data &h0BB268D9, &h2C2D6C5E, &hA0D79121, &h224FA910, &h688624C1, &h6B9A3744
Data &h4F6D5D31, &h531EEDF7, &h92DEE265, &h8157D4F3, &h8CF28A2D, &hBA11082A
Data &h709F1742, &hEDC38D0F, &h623F0D21, &h25C0B2B6, &h2621B669, &hE0FCDEB8
Data &h5171637D, &hCA6FAEBD, &h6EBF6066, &h85A7513B, &hEBF57225, &h06F32CFA
Data &h6AD0A267, &h74C9F4F1, &h62829071, &h9084749C, &h03DB589F, &hB3153DC3
Data &h25746B82, &h7FC1B811, &h7C9A4D2F, &hA7694F9B, &hE5655A0D, &hFC44F556
Data &hDD4EE5BE, &hD79E71B3, &h05B2088B, &hCCB8F967, &h5F10DB32, &hDABAF532
Data &hB0E06ABC, &h3329DE1D, &hE213ABA4, &h8BAFDB4D, &h2DD6D2ED, &h2057FF95
Data &hC5867C28, &h3106837E, &hEC1CEA13, &h040E8977, &h36440A9E, &h0AE38194
Data &h2B416AEF, &h356D2F10, &hA970ABB8, &hEAAC4895, &h7F19B871, &h9C5C0BBF
Data &hBB83E625, &h6E1ED30E, &h76B2EA2A, &h7AEF1273, &h20CF9778, &h0FC2ABA7
Data &h404D39E6, &h062374EA, &hF171619F, &hF3639C72, &hE9A217BE, &hB8974624
Data &h5D00BA6C, &h470E5775, &h7DF1A481, &hE48B7C0A, &hDEE191A7, &hFFF36C44
Data &h1012F444, &hE2E03546, &h2A042C39, &hEA91B32D, &hC42F27DB, &hB67AB929
Data &h89AFABDD, &h551D42AF, &hE31B574F, &h2561F74C, &hB6C45887, &h7FACCE8E
Data &hC1E825C9, &h30ACA6EB, &h9778F48C, &h7C427465, &h55D610CB, &hE1023DF7
Data &hDA393427, &hE0FCD959, &h5EC2CCC9, &h4C1472F3, &h548E9020, &h75D0A2B8
Data &h3DA2083B, &h56A194AC, &hCCF8BEE5, &h63AC57CA, &h19B59D5A, &hA1B49471
Data &hF61D061D, &h1725FAE9, &h31572820, &hC5710943, &hB516F2A1, &h0A5BE645
Data &h2113B61A, &h4C49A997, &h3001A510, &h32398B2E, &h8856B82A, &h71286763
Data &h49036463, &h980292E3, &h3E8838F6, &h708A3231, &h692137B4, &hF82C6974
Data &h5BC51872, &hB545F7FF, &hBEF94959, &hD08BB987, &h8FA37192, &h38F55B14
Data &h6D905E2F, &h39A8DAC4, &hE68F12AF, &h25A8509A, &hA67A971F, &h69363234
Data &hC714420A, &h21FEA4C9, &hE710B91E, &hF3945EEC, &hDCAAB4E6, &h3C4B93E6
Data &h80E808E6, &h7B0946B7, &h88BAC85E, &h93A9E058, &hFC729675, &h2042EFD6
Data &h92579531, &h9357CF75, &h8BB9E10A, &h94B5D0F1, &hFACDDEC8, &h8A53D96C
Data &h4EBE77DD, &h9F25EDDB, &h15448866, &h395C31EF, &h2A2F7906, &hFF9529D8
Data &hB63B92DA, &h6F4FBC5D, &h29F349E9, &h320909B0, &h829536E6, &h0001D4F8
Data &hB7802008, &h4B6AFBAE, &hD07FF582, &hDCA933E5, &h7055630A, &hBDCE0EE7
Data &hA885D15D, &h25D0A20C, &h132E6527, &h6B8268D6, &h6B81115C, &hFCDA9851
Data &hF3F2B2E8, &hBF4EA3F2, &hF4B5EB87, &hF3EF4371, &h532B4FAD, &h5DA7C9C9
Data &h85796C11, &h4315CD86, &h3D96D505, &hC098CCE1, &hEC5B20F8, &h7D423399
Data &h308F8343, &h6DE1C1A7, &h236BA762, &h419E81F9, &h7818EDD6, &hCFF9472D
Data &h2861F8E2, &hB80D0046, &h28C6E75F, &h14C7180C, &h0876BE10, &h6B5977F6
Data &h3DE7A696, &h08DD1461, &h36157D88, &h477880AE, &h2F8F9CA5, &h63420DD1
Data &hC3F8BB99, &hE5737AD9, &h1BB929BD, &hB80628B4, &h41C175FB, &h8899C29E
Data &h1B8AEF9D, &h8BE55727, &hACCB23CB, &hB2093546, &h2B4D1C11, &h456408FE
Data &h8E28CA26, &h6F7CFE0C, &h8A9C9366, &hA5D8F119, &h86668302, &h5E11D1AB
Data &h8CF63837, &h27ACAF5E, &hBFCB5D2D, &h42C7B97A, &h386C3AE9, &h8E348A68
Data &h3E77721C, &h27275E81, &h03B18F1C, &hF8389DB2, &hE241328D, &hDCCD185A
Data &h60690244, &h25679B5D, &h23B9AB3D, &hFB90AEA4, &h7257B3E8, &h17BDA0D8
Data &h801986C1, &h64D14C0B, &h76789DDA, &h095DA843, &hD95EF5F6, &h684CA4B1
Data &h5CEADB15, &hF12FD4AA, &h9460F12B, &hF0450E5E, &h967EE85F, &h35CC98CE
Data &h91B7C506, &h708AD1C1, &h3D121A0B, &hF8345D48, &h13574BF6, &h4925EB46
Data &h6E28C346, &h45018B3D, &hE3A13956, &h2F0273C4, &hAA0FBDA6, &h52013A07
Data &h30B0C5D7, &h8072C882, &h2045EB25, &h69A2F9BD, &h3F28F33B, &hB6040287
Data &h5D1C6226, &h07020EC2, &h2E137CF5, &h19C8E6B9, &h3D865FF5, &hDF525307
Data &hF4A8D9E2, &hA27C3026, &hD4B764BF, &hA3728266, &hCDEF6A82, &h375DB5F5
Data &h877A82DE, &hAA902D93, &hE78A347B, &h0E759562, &h38782939, &h9C4DC5D1
Data &hE73F3B13, &hFBE1028E, &hA31AB704, &h80BA6B82, &hEEFB6841, &h32AD2E9A
Data &h3379787D, &h5D1A8EA6, &h349EC27F, &hC9834908, &h325CF6A9, &h39912F76
Data &h36AD323E, &h2E63E92B, &h2257C386, &h5AAECB30, &h4A4F93E1, &h687F59A1
Data &hE27BAB82, &hAEA05F7D, &hB413CAAA, &h9F2932E2, &h644C2EC8, &h8CDD4971
Data &hA7891097, &h26D39445, &h9C7A74A3, &h0468AE55, &h55A3E4EB, &hB26AA07E
Data &hA436BB69, &hC9E026AA, &h34736609, &h534CB63C, &hF748C377, &hB168A492
Data &h90959C3A, &h0A6FD765, &h0EFEC5F8, &h270D2E4D, &hB3982403, &h43EB047E
Data &h036E80B7, &h23FA9938, &hDEEE0755, &h2E3396F8, &hEB92F48B, &h3B63BB2A
Data &h66700E4B, &hADDC6127, &h1F4A8640, &h596A173E, &h79C2EDBF, &h3D5A9CA3
Data &h88B5BC85, &hA7F259F6, &h0D7976B9, &hC3569BAD, &h5018ECAF, &h7F46D40C
Data &h9FDBC30A, &h3E1F5FA2, &h17D8ED1C, &h9097CE1B, &hB3BB3EA9, &hDF5DF178
Data &hA60317F8, &h712B1B5B, &hB6556FEF, &h6B7B39F1, &h8D02114F, &h39F3EA6D
Data &h66D926FD, &h70547778, &h15073906, &h7A01CFF4, &h00655921, &h87183CA1
Data &h3E3FDCD3, &h4691ACF4, &h9C380003, &h0B62C83A, &h3559EEBB, &hE91FB0FF
Data &hAABCA07E, &h3FC4EA20, &hA910A92D, &hC1E729ED, &hDC627E83, &h5F5C5946
Data &h3C93EADA, &h513ACDCB, &hBAD5D6BD, &hD0638D67, &h273815F9, &hDB3A6C6D
Data &h8EBB102E, &hBD83D8B5, &h8F020215, &hBD31352E, &h13FCFDCA, &hEFE3E759
Data &h09964918, &h8B1B8D09, &h0BF8CD71, &hA5216866, &hE3DE8486, &h9C9DBE4D
Data &h781937D2, &hEAFCCFB1, &hA7540E5B, &hD9B3C780, &h3E72A8F7, &h4D440E4D
Data &hD2662B12, &hC8CC6D24, &h1875FC18, &hE0B21D7B, &hD66A4F23, &h2687A3C0
Data &h5816EA5A, &h5E92FB4D, &h5178FAA1, &h720B9FED, &hF6E73146, &hF766B40E
Data &h08ABA231, &h5CA4C09F, &hCA85E822, &hC52AE253, &hC181EC65, &hF5F892CA
Data &h249450E0, &h543DF48B, &h479E4FB8, &h4CBA15F3, &hD9B40518, &hE3EB453E
Data &hDFDE6DC7, &hE0AFA109, &h45DFA930, &hE3734B0E, &h6DBA575A, &h0C3387F8
Data &hEDA31531, &h8634D7B4, &hB89EAEDF, &h72633789, &hF1A4E6C6, &hBA78FAD2
Data &h8593F7DA, &h4EC997C1, &hFFEC6A2E, &h3FDBC0D4, &h34B7F0A4, &hE8477BA4
Data &hCD701C82, &h47093810, &h3791AB66, &hBEC966E6, &h837CCB20, &h01954403
Data &hB3549E09, &hE37312B0, &hB216AD52, &hD89A75C0, &h6DBE6CE1, &h365D65D3
Data &h49F92BC8, &h503C7118, &h3E0A54E8, &hB9C2CA3D, &hB796830C, &hA3FFD82B
Data &h637C99A6, &h409196A9, &h0F4CD9DF, &h8A8785DC, &h26A68CFB, &h8F9D9519
Data &h8692EE07, &h7FA3B876, &h3583B483, &h4405DB89, &hECC73393, &hB7851467
Data &h91914C3C, &h05A0785B, &h4ED8A843, &hCEBC2238, &h964E4A12, &hD35F3CD3
Data &h4EC4ACB9, &hCF56AB46, &h2870AC3E, &hB68F844D, &h61E35212, &h9A2D761B
Data &h21563F4A, &hE393C2C6, &hE19B3AA2, &hDEE81972, &h506194F3, &h5330B6CE
Data &h41808025, &hCEAAD2F6, &h857A6480, &h50B169DF, &h7905FD2B, &hD0B95040
Data &hD3983D9C, &h52E9D9F6, &h539BD10E, &h370CBAFE, &hD11C449C, &h4C720EA3
Data &h4B0C0D09, &h277E6D50, &hE3E90E88, &h916F7170, &hAF18C5DC, &h9E562621
Data &h190FF173, &h6FC0D5C8, &hADEB40AA, &hA6F62064, &h285355E6, &h6E8F004B
Data &h37579904, &hB70C5107, &h7FBC54AD, &h4B039544, &hEED9C1D8, &h1CB55376
Data &h2EFEA92A, &hF12075B8, &hA2433873, &h6D2C803B, &h34C5FA17, &h2E591F37
Data &h61FB29DB, &h626BC5C7, &h844F4BAD, &h2E41BF5E, &h6ABCB2D7, &h08996BA4
Data &hD1B47F5B, &h4B7F31FE, &hE8E218C4, &h62889BC8, &h034EAF00, &h33CDF1C8
Data &h7859D3E4, &hFE7A2845, &h384EEE9D, &h197B10A0, &hF202AC8B, &h7498EA10
Data &hC284ADBC, &h85DFB332, &h2CCDEEDB, &hE1518D0C, &h8460FCC9, &hBE314707
Data &h6C271C9E, &h8A29B982, &h60E36E4A, &hBBDEC90D, &h2635FC9B, &h25DDCAD8
Data &hEC434C14, &hD88273DF, &hDD604975, &h6F70603D, &hBBA8EA18, &hC9644D06
Data &hB45D4E47, &h6F1380A9, &h602395F5, &hDA475D5E, &h00D8A89C, &h1CD2CF60
Data &hF214FAA4, &h7AA820D9, &h65669C37, &hC9564596, &h024BF655, &h4D753333
Data &hF6CDC673, &h5D7032D4, &hAB69E65B, &h2CF505DA, &hB4793639, &h89A5D276
Data &h03B1DC73, &h9B391BE8, &hCCCBF12F, &h35AC8289, &hB6949CA8, &h20397EC9
Data &h9109095B, &h64AC0181, &h6229474F, &hDEA0D561, &hE0E50782, &h4D94C197
Data &h8ED5379A, &h76E7CC80, &h3D1D9E9F, &h09957575, &h23AE1A12, &h88A3FB73
Data &h9734919B, &h69A54C26, &hF4D902CF, &h6AAD97D9, &h228CB15A, &h78D68C1C
Data &hC8D8A390, &h19D4EB32, &h481E8FD5, &h8154B8CB, &h3528AC84, &hF59D9268
Data &h81EEDE31, &h65A51F5C, &h1A647996, &h1CEF6439, &hEC5DA295, &h14A0520E
Data &h95C795C8, &hC9EA6EF7, &h559528A3, &hE087930A, &hB5C81488, &hB3F48186
Data &hA6AA9BC3, &hE7D9C772, &hB9755899, &h9CAFE63F, &h685EF69B, &h1F3F237D
Data &h6F32BCEE, &hAC50F81D, &hB89C998C, &h60219A12, &h7817EF87, &hA293599B
Data &hF392A3A7, &h69C1B6F8, &hB7D591D0, &h96FC1150, &hA4E3D2DC, &h3E908B71
Data &h31F41E41, &h90EA1BA1, &h5E87DB6B, &h3FEDCE2E, &h5A2549EA, &h71569C46
Data &h70BBE34F, &h65D24027, &h4F8DDDD7, &hAC61AC6B, &hD4F33396, &h6E7379E7
Data &hC077A58E, &hE9F2E533, &hFA67084B, &h8CA350F4, &h8867412A, &h7D6FC0CC
Data &hDEA2161E, &h85D36AAB, &hA586B1F7, &h62DCEA2D, &hCD3807CC, &h8129F6BA
Data &h84D91848, &h1334361E, &hF664C270, &h6BA207B1, &h9E9D9D86, &h25BB9AA4
Data &h24683B50, &hC9DC6896, &h71E27063, &h961F3BDF, &h97848FF4, &h66A50780
Data &h332A8C6A, &hD278B2C6, &h02098892, &h9E6D4199, &h787667FA, &hB4091AB3
Data &h99233685, &h30230D4D, &h3EEE67CC, &hBACD99F7, &h72B74E41, &hAE56C5EC
Data &h792D8014, &hE3B8835B, &h239C1EB1, &h917BF2FA, &h5EC92B8F, &h43F1FB39
Data &hD6AAC0AE, &h9DBB6694, &h68385320, &h7958D47D, &hD74F382F, &h0AED6BE6
Data &h504B385A, &h7EB1F5D1, &h176DC187, &h7806522C, &h1DF647DC, &h28973B4B
Data &h12EA784F, &h7DD5057A, &h1DB40510, &h6534D42F, &hCBB6B343, &h37729ECE
Data &h975FB6FC, &h5A117842, &h8E77BDB9, &hABA5121C, &hA3B706A8, &hB086CCE1
Data &hD9BA3CA1, &h2B0FEE61, &hB6DE3D39, &hBC6DF5E6, &h4C8894B3, &hF81EECAE
Data &hBBCF1112, &h21580E22, &hA51D0E94, &hCC1EAD08, &h1CA9D6B2, &h0E783631
Data &h65A1D33D, &h96AD6477, &hD3E6E10D, &h96A87C39, &h76C74AE2, &hD17FD74E
Data &h5682A7A2, &h50F2A032, &h1C273843, &h9511CED5, &h2B6B37F0, &h9D9F2E44
Data &h18FACAAA, &h0199550D, &hBA206C92, &h5CD9D127, &hB3ACC553, &h2B545C94
Data &hDE973173, &hDFCFCB69, &hA1D5B4F2, &h3CB4DB5B, &h98D525B8, &h97B4B0DC
Data &hB48B600B, &h1B76995F, &hC091B480

#If NUM_DWORDS<=10382
   restore BigFloat_pi_bf_data
   for i as long=0 to NUM_DWORDS
      read pi_bf.BigNum.mantissa[i]
   next
   pi_bf.BigNum.exponent=&h40000002
   pi_bf.BigNum.sign=0
#elseif NUM_DWORDS>10382
   restore BigFloat_pi_bf_data
   for i as long=0 to 10382
      read pi_bf.BigNum.mantissa[i]
   next
   pi_bf.BigNum.exponent=&h40000002
   pi_bf.BigNum.sign=0
#Endif

pi2_bf.BigNum = fpadd(pi_bf.BigNum, pi_bf.BigNum)
pi_bf_half.BigNum = fpdiv_si( pi_bf.BigNum, 2)
pi_bf_quarter.BigNum = fpdiv_si( pi_bf.BigNum, 4)

Dim Shared As BigFloat tan_half_num(15), tan_half_den(14)

tan_half_num(0).BigNum.mantissa[0]=&h1F000000
tan_half_num(0).BigNum.exponent=&h4000000A
tan_half_num(0).BigNum.sign=0

tan_half_num(1).BigNum.mantissa[0]=&h133D2F80
tan_half_num(1).BigNum.exponent=&h4000001C
tan_half_num(1).BigNum.sign=0

tan_half_num(2).BigNum.mantissa[0]=&h1BF6B6C2
tan_half_num(2).BigNum.mantissa[1]=&h74000000
tan_half_num(2).BigNum.exponent=&h4000002B
tan_half_num(2).BigNum.sign=0

tan_half_num(3).BigNum.mantissa[0]=&h1291BABB
tan_half_num(3).BigNum.mantissa[1]=&h4E673000
tan_half_num(3).BigNum.exponent=&h4000003A
tan_half_num(3).BigNum.sign=0

tan_half_num(4).BigNum.mantissa[0]=&h1B1C425E
tan_half_num(4).BigNum.mantissa[1]=&hF5B72654
tan_half_num(4).BigNum.exponent=&h40000047
tan_half_num(4).BigNum.sign=0

tan_half_num(5).BigNum.mantissa[0]=&h17EF4958
tan_half_num(5).BigNum.mantissa[1]=&hA94EC220
#if NUM_DWORDS>1
   tan_half_num(5).BigNum.mantissa[2]=&h3C400000
#endif
tan_half_num(5).BigNum.exponent=&h40000054
tan_half_num(5).BigNum.sign=0

tan_half_num(6).BigNum.mantissa[0]=&h1AEE4574
tan_half_num(6).BigNum.mantissa[1]=&hFBE2A969
#if NUM_DWORDS>1
   tan_half_num(6).BigNum.mantissa[2]=&hB1891000
#endif
tan_half_num(6).BigNum.exponent=&h40000060
tan_half_num(6).BigNum.sign=0

tan_half_num(7).BigNum.mantissa[0]=&h13D4ED41
tan_half_num(7).BigNum.mantissa[1]=&h4EB3C0A5
#if NUM_DWORDS>1
   tan_half_num(7).BigNum.mantissa[2]=&hEBF80596
#endif
tan_half_num(7).BigNum.exponent=&h4000006C
tan_half_num(7).BigNum.sign=0

tan_half_num(8).BigNum.mantissa[0]=&h13469AD6
tan_half_num(8).BigNum.mantissa[1]=&hE36FE3D5
#if NUM_DWORDS>1
   tan_half_num(8).BigNum.mantissa[2]=&hF9F12FC8
#endif
#if NUM_DWORDS>2
   tan_half_num(8).BigNum.mantissa[3]=&h44000000
#endif
tan_half_num(8).BigNum.exponent=&h40000077
tan_half_num(8).BigNum.sign=0

tan_half_num(9).BigNum.mantissa[0]=&h188AF3E4
tan_half_num(9).BigNum.mantissa[1]=&h14355DDF
#if NUM_DWORDS>1
   tan_half_num(9).BigNum.mantissa[2]=&h051C8664
#endif
#if NUM_DWORDS>2
   tan_half_num(9).BigNum.mantissa[3]=&h1FD20000
#endif
tan_half_num(9).BigNum.exponent=&h40000081
tan_half_num(9).BigNum.sign=0

tan_half_num(10).BigNum.mantissa[0]=&h13FA03D4
tan_half_num(10).BigNum.mantissa[1]=&h5BFDD67E
#if NUM_DWORDS>1
   tan_half_num(10).BigNum.mantissa[2]=&h0354F5F5
#endif
#if NUM_DWORDS>2
   tan_half_num(10).BigNum.mantissa[3]=&h8DABEE00
#endif
tan_half_num(10).BigNum.exponent=&h4000008B
tan_half_num(10).BigNum.sign=0

tan_half_num(11).BigNum.mantissa[0]=&h13DC9031
tan_half_num(11).BigNum.mantissa[1]=&hE02034BF
#if NUM_DWORDS>1
   tan_half_num(11).BigNum.mantissa[2]=&h417479B6
#endif
#if NUM_DWORDS>2
   tan_half_num(11).BigNum.mantissa[3]=&h71902F42
#endif
tan_half_num(11).BigNum.exponent=&h40000094
tan_half_num(11).BigNum.sign=0

tan_half_num(12).BigNum.mantissa[0]=&h164D8A73
tan_half_num(12).BigNum.mantissa[1]=&hBD464C4C
#if NUM_DWORDS>1
   tan_half_num(12).BigNum.mantissa[2]=&h18F7979B
#endif
#if NUM_DWORDS>2
   tan_half_num(12).BigNum.mantissa[3]=&h44DAF955
#endif
#if NUM_DWORDS>3
   tan_half_num(12).BigNum.mantissa[4]=&h50000000
#endif
tan_half_num(12).BigNum.exponent=&h4000009C
tan_half_num(12).BigNum.sign=0

tan_half_num(13).BigNum.mantissa[0]=&h189DFF47
tan_half_num(13).BigNum.mantissa[1]=&hBFC96330
#if NUM_DWORDS>1
   tan_half_num(13).BigNum.mantissa[2]=&h4D32ECC6
#endif
#if NUM_DWORDS>2
   tan_half_num(13).BigNum.mantissa[3]=&h265BF3D2
#endif
#if NUM_DWORDS>3
   tan_half_num(13).BigNum.mantissa[4]=&h2A400000
#endif
tan_half_num(13).BigNum.exponent=&h400000A3
tan_half_num(13).BigNum.sign=0

tan_half_num(14).BigNum.mantissa[0]=&h141F6AC2
tan_half_num(14).BigNum.mantissa[1]=&hECEDD74E
#if NUM_DWORDS>1
   tan_half_num(14).BigNum.mantissa[2]=&h5710A461
#endif
#if NUM_DWORDS>2
   tan_half_num(14).BigNum.mantissa[3]=&hF90CE5F7
#endif
#if NUM_DWORDS>3
   tan_half_num(14).BigNum.mantissa[4]=&h39140000
#endif
tan_half_num(14).BigNum.exponent=&h400000A9
tan_half_num(14).BigNum.sign=0

tan_half_num(15).BigNum.mantissa[0]=&h14754624
tan_half_num(15).BigNum.mantissa[1]=&h0A7A56A0
#if NUM_DWORDS>1
   tan_half_num(15).BigNum.mantissa[2]=&hB661FC74
#endif
#if NUM_DWORDS>2
   tan_half_num(15).BigNum.mantissa[3]=&hAC227254
#endif
#if NUM_DWORDS>3
   tan_half_num(15).BigNum.mantissa[4]=&hF17F0000
#endif
tan_half_num(15).BigNum.exponent=&h400000AC
tan_half_num(15).BigNum.sign=0

'=============================================

tan_half_den(0).BigNum.mantissa[0]=&h1DF88000
tan_half_den(0).BigNum.exponent=&h40000013
tan_half_den(0).BigNum.sign=0

tan_half_den(1).BigNum.mantissa[0]=&h12698E75
tan_half_den(1).BigNum.mantissa[1]=&h80000000
tan_half_den(1).BigNum.exponent=&h40000024
tan_half_den(1).BigNum.sign=0

tan_half_den(2).BigNum.mantissa[0]=&h11838476
tan_half_den(2).BigNum.mantissa[1]=&h73FC0000
tan_half_den(2).BigNum.exponent=&h40000033
tan_half_den(2).BigNum.sign=0

tan_half_den(3).BigNum.mantissa[0]=&h10F934AF
tan_half_den(3).BigNum.mantissa[1]=&h35AA51E0
tan_half_den(3).BigNum.exponent=&h40000041
tan_half_den(3).BigNum.sign=0

tan_half_den(4).BigNum.mantissa[0]=&h131AB6C5
tan_half_den(4).BigNum.mantissa[1]=&h51271035
#if NUM_DWORDS>1
   tan_half_den(4).BigNum.mantissa[2]=&h98000000
#endif
tan_half_den(4).BigNum.exponent=&h4000004E
tan_half_den(4).BigNum.sign=0

tan_half_den(5).BigNum.mantissa[0]=&h1ACD48CC
tan_half_den(5).BigNum.mantissa[1]=&h9D96DC0C
#if NUM_DWORDS>1
   tan_half_den(5).BigNum.mantissa[2]=&h18CD0000
#endif
tan_half_den(5).BigNum.exponent=&h4000005A
tan_half_den(5).BigNum.sign=0

tan_half_den(6).BigNum.mantissa[0]=&h18588B5C
tan_half_den(6).BigNum.mantissa[1]=&h9CDA0C94
#if NUM_DWORDS>1
   tan_half_den(6).BigNum.mantissa[2]=&hB1110CC0
#endif
tan_half_den(6).BigNum.exponent=&h40000066
tan_half_den(6).BigNum.sign=0

tan_half_den(7).BigNum.mantissa[0]=&h1D20BC77
tan_half_den(7).BigNum.mantissa[1]=&hEB9802F3
#if NUM_DWORDS>1
   tan_half_den(7).BigNum.mantissa[2]=&hB2944834
#endif
#if NUM_DWORDS>2
   tan_half_den(7).BigNum.mantissa[3]=&h50000000
#endif
tan_half_den(7).BigNum.exponent=&h40000071
tan_half_den(7).BigNum.sign=0

tan_half_den(8).BigNum.mantissa[0]=&h16F4FA2F
tan_half_den(8).BigNum.mantissa[1]=&hED17ECAD
#if NUM_DWORDS>1
   tan_half_den(8).BigNum.mantissa[2]=&hF373B0E8
#endif
#if NUM_DWORDS>2
   tan_half_den(8).BigNum.mantissa[3]=&h49E00000
#endif
tan_half_den(8).BigNum.exponent=&h4000007C
tan_half_den(8).BigNum.sign=0

tan_half_den(9).BigNum.mantissa[0]=&h177812D2
tan_half_den(9).BigNum.mantissa[1]=&h19B96E90
#if NUM_DWORDS>1
   tan_half_den(9).BigNum.mantissa[2]=&h767CE082
#endif
#if NUM_DWORDS>2
   tan_half_den(9).BigNum.mantissa[3]=&hF1A0D000
#endif
tan_half_den(9).BigNum.exponent=&h40000086
tan_half_den(9).BigNum.sign=0

tan_half_den(10).BigNum.mantissa[0]=&h1E14144F
tan_half_den(10).BigNum.mantissa[1]=&hBEDFA752
#if NUM_DWORDS>1
   tan_half_den(10).BigNum.mantissa[2]=&h196160E1
#endif
#if NUM_DWORDS>2
   tan_half_den(10).BigNum.mantissa[3]=&hB9AD0DA0
#endif
tan_half_den(10).BigNum.exponent=&h4000008F
tan_half_den(10).BigNum.sign=0

tan_half_den(11).BigNum.mantissa[0]=&h16C20FE3
tan_half_den(11).BigNum.mantissa[1]=&hD0CF91C5
#if NUM_DWORDS>1
   tan_half_den(11).BigNum.mantissa[2]=&hD0557621
#endif
#if NUM_DWORDS>2
   tan_half_den(11).BigNum.mantissa[3]=&h0CCA8B7B
#endif
#if NUM_DWORDS>3
   tan_half_den(11).BigNum.mantissa[4]=&hA0000000
#endif
tan_half_den(11).BigNum.exponent=&h40000098
tan_half_den(11).BigNum.sign=0

tan_half_den(12).BigNum.mantissa[0]=&h1255E6BF
tan_half_den(12).BigNum.mantissa[1]=&h26AEB757
#if NUM_DWORDS>1
   tan_half_den(12).BigNum.mantissa[2]=&h2D242A2D
#endif
#if NUM_DWORDS>2
   tan_half_den(12).BigNum.mantissa[3]=&h2FFDDE36
#endif
#if NUM_DWORDS>3
   tan_half_den(12).BigNum.mantissa[4]=&h23000000
#endif
tan_half_den(12).BigNum.exponent=&h400000A0
tan_half_den(12).BigNum.sign=0

tan_half_den(13).BigNum.mantissa[0]=&h19EF9AAB
tan_half_den(13).BigNum.mantissa[1]=&h97C67637
#if NUM_DWORDS>1
   tan_half_den(13).BigNum.mantissa[2]=&h75E7F050
#endif
#if NUM_DWORDS>2
   tan_half_den(13).BigNum.mantissa[3]=&hC3D7BC4F
#endif
#if NUM_DWORDS>3
   tan_half_den(13).BigNum.mantissa[4]=&hB5A80000
#endif
tan_half_den(13).BigNum.exponent=&h400000A6
tan_half_den(13).BigNum.sign=0

tan_half_den(14).BigNum.mantissa[0]=&h14754624
tan_half_den(14).BigNum.mantissa[1]=&h0A7A56A0
#if NUM_DWORDS>1
   tan_half_den(14).BigNum.mantissa[2]=&hB661FC74
#endif
#if NUM_DWORDS>2
   tan_half_den(14).BigNum.mantissa[3]=&hAC227254
#endif
#if NUM_DWORDS>3
   tan_half_den(14).BigNum.mantissa[4]=&hF17F0000
#endif
tan_half_den(14).BigNum.exponent=&h400000AB
tan_half_den(14).BigNum.sign=0

Function fptan_half(Byref x As bigfloat_struct, Byval dwords As Ulong = NUM_DWORDS) As bigfloat_struct
   If dwords > NUM_DWORDS Then dwords = NUM_DWORDS
   Dim As bigfloat_struct accum, x_, xx, thn, thd
   Dim As Long i, sign

   xx=fpmul(x, x, dwords)

   'the folowing is a rational polynomial for tan(x/2) derived from the continued fraction
   '                         x^2
   'tan(x/2) = 2 - -------------------------
   '                           x^2
   '              6 - ----------------------
   '                             x^2
   '                 10 - ------------------
   '                               x^2
   '                     14 - --------------
   '                                 x^2
   '                          18 - ---------
   '                                   x^2
   '                              22 - -----
   '                                   26 - ...

   ' and so on
   '
   'the nice quality of this expansion is that you can calculate sin, cos and tan very easily
   '
   'if y = tan(x/2) then
   '
   '          2*x*y
   'sin(x) = -------
   '         y^2+x^2
   '
   '          y^2-x^2
   'cos(x) = ---------
   '          y^2+x^2
   '
   '          2*x*y
   'tan(x) = -------
   '         y^2-x^2

   sign=-1
   thn=tan_half_num(0).BigNum
   For i=1 To 15
      thn=fpmul(xx, thn, dwords)
      If sign=1 Then
         thn=fpadd(thn, tan_half_num(i).BigNum, dwords)
      Else
         thn=fpsub(thn, tan_half_num(i).BigNum, dwords)
      End If
      sign=-sign
   Next

   thd=fpsub(xx, tan_half_den(0).BigNum, dwords)
   sign=1
   For i=1 To 14
      thd=fpmul(xx, thd, dwords)
      If sign=1 Then
         thd=fpadd(thd, tan_half_den(i).BigNum, dwords)
      Else
         thd=fpsub(thd, tan_half_den(i).BigNum, dwords)
      End If
      sign=-sign
   Next
   accum=fpdiv(thn,thd, dwords) 'tan(x/2)
   Return accum
End Function

Function mp_sin(Byref x As BigFloat_struct, Byval dwords As Ulong = NUM_DWORDS) As BigFloat_struct
   If dwords > NUM_DWORDS Then dwords = NUM_DWORDS
   Dim As BigFloat_struct ab, accum, factor, x_2, xx, p, tmp, tmp2
   Dim As BigFloat_struct thn, thd
   Dim As Long sign(0 To 3), c, limit, i, lim
   
   x_2=x

   ab=x
   ab.sign=0
   If fpcmp(ab, pi2_bf.BigNum, dwords)=1 Then
      '======== centralize ==============
      'floor/ceil to centralize

      tmp=fpdiv(x_2, pi2_bf.BigNum, dwords)
      tmp2=tmp
      tmp=fpfix(tmp)     'int part
      tmp=fpsub(tmp2, tmp, dwords) 'frac part
      tmp=fpmul(tmp, pi2_bf.BigNum, dwords)
      x_2=tmp
   End If
   '? fp2str(x_2, 16)
   '==================================
   limit=9.63*dwords
   If limit>10006 Then
      lim=limit
      limit=10006
   End If
   'if limit>10006 then limit=10006
   'limit = digits of precision, here's a polynomial fit to get an exstimate for limit
   'works well for precision from 60 to 10000 digits
   limit=1+Int(-0.45344993886092585968+0.022333002852398072433*limit+5.0461814408333079844e-7*limit*limit-4.2338453039804235772e-11*limit*limit*limit)
   
   If lim<>0 Then
      limit=lim/10000*limit
   End If
   
   If limit<0 Then limit=0
   factor=si2fp(5, dwords)

   For i=1 To limit
      factor=fpmul_si(factor, 5, dwords)
   Next
   'factor=factor^limit

   x_2=fpdiv(x_2,factor, dwords)  'x_2=x_2/5^limit
   accum=fptan_half(x_2, dwords)
   xx=fpmul(x_2, x_2, dwords)

   'now convert to sin(x)
   tmp=fpmul_si(x_2, 2, dwords)
   tmp=fpmul(tmp, accum, dwords)
   tmp2=fpmul(accum, accum, dwords)
   tmp2=fpadd(tmp2, xx, dwords)
   accum=fpdiv(tmp, tmp2, dwords)
   
   'multiply the result by 5^limit

   For i=1 To limit+1
      tmp=fpmul(accum, accum, dwords)
      tmp2=fpmul(accum, tmp, dwords)
      'sin(5*x) = 5 * sin(x) - 20 * sin(x)^3 + 16 * sin(x)^5
      accum=fpmul_si(accum, 5, dwords)
      accum=fpsub(accum, fpmul_si(tmp2, 20, dwords), dwords)
      tmp=fpmul(tmp2, tmp, dwords)
      accum=fpadd(accum, fpmul_si(tmp, 16, dwords), dwords)
   Next i

   Return accum
End Function

Function mp_cos (Byref x As BigFloat_struct, Byval dwords As Ulong = NUM_DWORDS) As BigFloat_struct
   If dwords > NUM_DWORDS Then dwords = NUM_DWORDS
   Dim As BigFloat_struct ab, accum, factor, x_2, xx, p, tmp, tmp2
   Dim As BigFloat_struct thn, thd
   Dim As Long sign(0 To 3), c, limit, i, lim

   x_2=fpadd(pi_bf_half.BigNum, x, dwords)

   ab=x_2 :ab.sign=0
   If fpcmp(ab, pi2_bf.BigNum, dwords)=1 Then
      '======== centralize ==============
      'floor/ceil to centralize

      tmp=fpdiv(x_2, pi2_bf.BigNum, dwords)
      tmp2=tmp
      tmp=fpfix(tmp)     'int part
      tmp=fpsub(tmp2, tmp, dwords) 'frac part
      tmp=fpmul(tmp, pi2_bf.BigNum, dwords)
      x_2=tmp
   End If
   '==================================
   limit=9.63*dwords
   If limit>10006 Then
      lim=limit
      limit=10006
   End If
   'limit = digits of precision, here's a polynomial fit to get an exstimate for limit
   'works well for precision from 60 to 10000 digits
   limit=1+Int(-0.45344993886092585968+0.022333002852398072433*limit+5.0461814408333079844e-7*limit*limit-4.2338453039804235772e-11*limit*limit*limit)
   
   If lim<>0 Then
      limit=lim/10000*limit
   End If
   
   If limit<0 Then limit=0
   factor=si2fp(5, dwords)

   For i=1 To limit
      factor=fpmul_si(factor, 5, dwords)
   Next
   'factor=factor^limit

   x_2=fpdiv(x_2,factor, dwords)  'x_2=x_2/5^limit
   accum=fptan_half(x_2, dwords)
   xx=fpmul(x_2, x_2, dwords)

   'now convert to sin(x)
   tmp=fpmul_si(x_2, 2, dwords)
   tmp=fpmul(tmp, accum, dwords)
   tmp2=fpmul(accum, accum, dwords)
   tmp2=fpadd(tmp2, xx, dwords)
   accum=fpdiv(tmp, tmp2, dwords)
   
   'multiply the result by 5^limit

   For i=1 To limit+1
      tmp=fpmul(accum, accum, dwords)
      tmp2=fpmul(accum, tmp, dwords)
      'sin(5*x) = 5 * sin(x) - 20 * sin(x)^3 + 16 * sin(x)^5
      accum=fpmul_si(accum, 5, dwords)
      accum=fpsub(accum, fpmul_si(tmp2, 20, dwords), dwords)
      tmp=fpmul(tmp2, tmp, dwords)
      accum=fpadd(accum, fpmul_si(tmp, 16, dwords), dwords)
   Next i

   Return accum
End Function

Function mp_tan(Byref x As BigFloat_struct, Byval dwords As Ulong = NUM_DWORDS) As BigFloat_struct
   If dwords > NUM_DWORDS Then dwords = NUM_DWORDS
   Dim As BigFloat_struct ab, accum, factor, x_2, xx, p, pi, pi2, circ, tmp, tmp2
   Dim As BigFloat_struct thn, thd
   Dim As Long c, limit, i, sign, lim
   pi=pi_bf.BigNum
   pi2=pi_bf_half.BigNum 'pdiv_si(pi_bf.BigNum, 2, dwords)

   x_2=x   

   'calculate the sign of tan(x)
   'if integer part of x/(pi/2) is odd then the sign is negative
   'unless x is negative then the sign is positive
   sign=fpfix_is_odd(fpdiv(x,pi2, dwords))

   If sign=1 Then
      sign=&h8000
   End If
   circ=pi2_bf.BigNum 'fpmul_si(pi, 2, dwords)

   ab=x :ab.sign=0

   If fpcmp(ab, circ, dwords)=1 Then
      '======== centralize ==============
      'floor/ceil to centralize

      pi=pi2_bf.BigNum 'fpadd(pi, pi, dwords) 'got 2*pi
      tmp=fpdiv(x_2, pi, dwords)
      tmp2=tmp
      tmp=fpfix(tmp)     'int part
      tmp=fpsub(tmp2, tmp, dwords) 'frac part
      tmp=fpmul(tmp, pi, dwords)
      x_2=tmp
   End If
   '==================================
   limit=dwords*9.63
   If limit>10006 Then
      lim=limit
      limit=10006
   End If
   'lm = dwords of precision, here's a polynomial fit to get an exstimate for limit
   'works well for precision from 60 to 10000 dwords
   limit=1+Int(-0.45344993886092585968+0.022333002852398072433*limit+5.0461814408333079844e-7*limit*limit-4.2338453039804235772e-11*limit*limit*limit)
   
   If lim<>0 Then
      limit=lim/10000*limit
   End If
   
   If limit<0 Then limit=0
   factor=si2fp(5, dwords)

   For i=1 To limit
      factor=fpmul_si(factor, 5, dwords)
   Next
   'factor=factor^limit

   x_2=fpdiv(x_2,factor, dwords)  'x_2=x_2/5^limit
   accum=fptan_half(x_2, dwords)
   xx=fpmul(x_2, x_2, dwords)

   'now convert to sin(x)
   tmp=fpmul_si(x_2, 2, dwords)
   tmp=fpmul(tmp, accum, dwords)
   tmp2=fpmul(accum, accum, dwords)
   tmp2=fpadd(tmp2, xx, dwords)
   accum=fpdiv(tmp, tmp2, dwords)

   'multiply the result by 5^limit

   For i=1 To limit+1
      tmp=fpmul(accum, accum, dwords)
      tmp2=fpmul(accum, tmp, dwords)
      'sin(5*x) = 5 * sin(x) - 20 * sin(x)^3 + 16 * sin(x)^5
      accum=fpmul_si(accum, 5, dwords)
      accum=fpsub(accum, fpmul_si(tmp2, 20, dwords), dwords)
      tmp=fpmul(tmp2, tmp, dwords)
      accum=fpadd(accum, fpmul_si(tmp, 16, dwords), dwords)
   Next i

   tmp=fpmul(accum, accum, dwords)
   tmp=fpsub(si2fp(1, dwords), tmp, dwords)
   tmp=fpsqr(tmp, dwords)
   tmp=fpdiv(accum, tmp, dwords)
   tmp.sign=sign Xor x.sign
   Return tmp
End Function

Function fpatn (Byref x As BigFloat_struct, Byval dwords As Ulong = NUM_DWORDS) As BigFloat_struct
   If dwords > NUM_DWORDS Then dwords = NUM_DWORDS
    Dim As Long sign(3): sign(3) = 1
    Dim As Long z, c = 1
    Dim As BigFloat_struct XX, Term, Accum, strC, x_2, mt, mt2, p
    Dim As BigFloat_struct Bignum, one, Bignum2, factor

    Bignum2 = x
    Bignum2.sign = 0
    one = si2fp(1, dwords)
    If fpcmp(Bignum2, one, dwords) = 0 Then
        Bignum = pi_bf_quarter.BigNum
        Bignum.sign = x.sign
        Return Bignum
    End If
    Bignum2.sign = x.sign
    Dim As Long limit = 16
    factor = si2fp(2 Shl (limit - 1), dwords)
    For z = 1 To limit
        Bignum = fpmul(Bignum2, Bignum2, dwords)
        Bignum = fpadd(Bignum, one, dwords)
        Bignum = fpsqr(Bignum, dwords)
        Bignum = fpadd(Bignum, one, dwords)
        Bignum = fpdiv(Bignum2, Bignum, dwords)
        Bignum2 = Bignum
    Next z

    mt = Bignum
    x_2 = Bignum
    p = Bignum
    XX = fpmul(x_2, x_2, dwords)
    Do
        c = c + 2
        mt2 = mt
        p = fpmul(p, XX, dwords)
        Term = fpdiv_si(p, c, dwords)
        If sign(c And 3) Then
            Accum = fpsub(mt, Term, dwords)
        Else
            Accum = fpadd(mt, Term, dwords)
        End If
        Swap mt, Accum
    Loop Until fpcmp(mt, mt2, dwords) = 0
    Return fpmul(factor, mt, dwords)
End Function

Function fpasin (Byref x As BigFloat_struct, Byval dwords As Ulong = NUM_DWORDS) As BigFloat_struct
   If dwords > NUM_DWORDS Then dwords = NUM_DWORDS
    Dim As Double num
    Dim As BigFloat_struct one, T, B, term1, minusone
    ' ARCSIN = ATN(x / SQR(-x * x + 1))
    '============= ARCSIN GUARD =========
   T = x
    one =si2fp(1, dwords)
    minusone = si2fp(-1, dwords)
    If fpcmp(T, one)>0 Then
      Return one
   End If
    If fpcmp(T, minusone)<0 Then
      Return minusone
    End If
    B = fpmul(x, x, dwords) 'x*x
    'for 1 and -1
    If fpcmp(B, one, dwords) = 0 Then
        Dim As BigFloat_struct two, Atn1
        two = si2fp(2, dwords)
        'atn1 = fpatn(one, dwords)
        If fpcmp(x, minusone, dwords) = 0 Then
            two = pi_bf_half.BigNum 'fpmul(two, atn1, dwords)
            two.sign =&h8000
            Return two 'fpmul(two, minusone, dwords)
        Else
            Return pi_bf_half.BigNum 'fpmul(two, atn1, dwords)
        End If
    End If
    B = fpsub(one, B, dwords) '1-x*x
    B = fpsqr(B, dwords) 'sqr(1-x*x)
    term1 = fpdiv(T, B, dwords)
    Return fpatn(term1, dwords)
End Function

Function fpacos (ByRef x As BigFloat_struct, ByVal dwords As ULong = NUM_DWORDS) As BigFloat_struct
   If dwords > NUM_DWORDS Then dwords = NUM_DWORDS
    Dim As BigFloat_struct one, minusone, two, Atn1, tail, T, B, term1, atnterm1, zero, ep

   ep.exponent=-(NUM_BITS-20)+BIAS+1
   ep.mantissa[0]=&h10000000ul
    'ARCCOS = ATN(-x / SQR(-x * x + 1)) + 2 * ATN(1)
    '========================
    one = si2fp(1, dwords)
    minusone = si2fp(-1, dwords)
    T=fpsub(x,one)
    T.sign=0
    If fpcmp(T, ep)<=0 Then
      Return zero
   End If
    If fpcmp(x, one)>=0 Then
      Return zero
   End If
    If fpcmp(x, minusone)<0 Then
      Return pi_bf.BigNum
    End If
    two = si2fp(2, dwords)
    Atn1 = pi_bf_quarter.BigNum
    tail = pi_bf_half.BigNum '2*atn(1)
    T = x : T.sign = T.sign Xor &h8000
    B = fpmul(x, x, dwords) 'x*x
    If fpcmp(B, one, dwords) = 0 Then
        'for 1 and -1
        If fpcmp(x, minusone, dwords) = 0 Then
            Return pi_bf.BigNum
        Else
            Return si2fp(0, dwords)
        End If
    End If
    B = fpsub(one, B, dwords) '1-x*x
    B = fpsqr(B, dwords) 'sqr(1-x*x)
    term1 = fpdiv(T, B, dwords)
    atnterm1 = fpatn(term1, dwords)
    Return fpadd(atnterm1, tail, dwords)
End Function

Function fplogTaylor(x As BigFloat_struct, Byval dwords As Long=NUM_DWORDS) As BigFloat_struct
   If dwords>NUM_DWORDS Then dwords=NUM_DWORDS
    'taylor series
    '====================Log Guard==================
    Dim As BigFloat_struct g,zero
    Dim As Integer i
    g=x : g.sign=0

    If fpcmp(g, x, dwords)<>0 Then  Return zero 'Exit Function
    If fpcmp(x, zero, dwords)=0 Then  Return zero 'Exit Function
    '=============================================
    Dim As Integer invflag
    Dim As  BigFloat_struct Inv,XX,Term,Accum,strC,_x,tmp,tmp2
    Dim As BigFloat_struct T,B,one,Q,two

   one.exponent=(BIAS+1)
   one.mantissa[0]=&h10000000
   two.exponent=(1+BIAS+1)
   two.mantissa[0]=&h10000000

    _x=x
    If fpcmp(x,one, dwords)<0 Then
        invflag=1
        _x=fpdiv(one, _x, dwords)
    End If
    T=fpsub(_x, one, dwords)
    B=fpadd(_x, one, dwords)
    accum=fpdiv(T, B, dwords)
    Q=fpdiv(T, B, dwords)
    tmp=Q
    XX=fpmul(Q, Q, dwords)
    Dim As Integer c=1
    Do 
        c=c+2
        tmp2=tmp
        Q=fpmul(Q, XX, dwords)
        term=fpdiv_si(Q,c, dwords)
        Accum=fpadd(tmp,Term, dwords)
        Swap tmp,Accum
    Loop Until fpcmp(tmp,tmp2, dwords) = 0
    accum=fpmul_si(accum,2, dwords)
    If invflag Then
      accum.sign=accum.sign Xor &h8000
    End If
    Return accum
End Function

Function fplog (x As BigFloat_struct, Byval dwords As Long=NUM_DWORDS) As BigFloat_struct
   If dwords>NUM_DWORDS Then dwords=NUM_DWORDS
    '====================Log Guard==================
    Dim As BigFloat_struct g, one, zero
    Dim As Integer i, factor

   one.exponent=(BIAS+1)
   one.mantissa[0]=&h10000000
    g=x
    If g.sign<>0 Then
      'Print "error: argument to Log is negative"
      Return zero
   End If
    g.sign=0
    If fpcmp(g, x, dwords)<>0 Then  Return zero 'Exit Function
    If fpcmp(x, zero, dwords)=0 Then  Return zero 'Exit Function
    If fpcmp(x, one, dwords)=0 Then  Return zero 'Exit Function
    '=============================================
    Dim As BigFloat_struct approx,ans,logx
    approx=x
    factor=8192 '4096
    approx=fpnroot(approx, factor, dwords)
    logx=fplogTaylor(approx, dwords)
    ans=fpmul_si(logx, factor, dwords)
    Return ans
End Function

Function fpexp (Byref x As BigFloat_struct, Byval dwords As Long=NUM_DWORDS) As BigFloat_struct
   If dwords>NUM_DWORDS Then dwords=NUM_DWORDS
    'taylor series
    Dim As  BigFloat_struct fac, x2, temp, accum, p, term, one
    Dim As Integer i, c, sign
   sign=x.sign
   one.exponent=(BIAS+1)
   one.mantissa[0]=&h10000000
   fac=one
   x2=x
   x2.sign=0
   If fpcmp(x2, temp, dwords)=0 Then Return fac
   c=1
    temp=fpdiv_si(x2, 8192, dwords) 'fpdiv_si(x, 67108864) '
    x2=temp
    p=x2
    accum=fpadd(fac, x2, dwords) '1 + x

    Do
        c+=1
        temp=accum
        fac=fpdiv_si(fac, c, dwords)
        p=fpmul(p, x2, dwords)
        term=fpmul(p,fac, dwords)
        Accum=fpadd(temp,Term, dwords)
    Loop Until fpcmp(accum,temp, dwords) <= 0
    For i=1 To 13
      accum=fpmul(accum, accum, dwords)
   Next
   If sign<>0 Then
      accum=fpdiv(one, accum, dwords)
   End If
    Return accum
End Function

Function fpsqr(Byref x As BigFloat_struct, Byval dwords As Long=NUM_DWORDS) As BigFloat_struct
   If dwords>NUM_DWORDS Then dwords=NUM_DWORDS
   Dim As BigFloat_struct ry, tmp, tmp2
   Dim As Double t, t1, t2
   Dim As Long i, ex, l, prec, p=2
   
   l=Log((NUMBER_OF_DIGITS+9.63)*0.0625)*1.5
   ex=(x.exponent And &h7FFFFFFF)-BIAS-1
   t=x.mantissa[0]+x.mantissa[1]/&h100000000
   t=t/&h10000000
   t1=Log(t)/p
   t2=0.6931471805599453*ex/p
   t1=Exp(t1)
   ry=dbl2fp(t2)
   ry=fpexp(ry,1)
   tmp=dbl2fp(t1)
   ry=fpmul(ry, tmp,1)
   prec=3

   tmp=fpdiv(x, ry, prec)
   tmp2=fpadd(ry, tmp, prec)
   ry=fpdiv_si(tmp2, p, prec)   

   For i=1 To l
      prec=2*prec-1
      tmp=fpdiv(x, ry, prec)
      tmp2=fpadd(ry, tmp, prec)
      ry=fpdiv_si(tmp2, p, prec)
   Next

   Return ry
End Function

Function fpnroot(Byref x As BigFloat_struct, Byval p As Long, Byval dwords As Long=NUM_DWORDS) As BigFloat_struct
   If dwords>NUM_DWORDS Then dwords=NUM_DWORDS
   Dim As BigFloat_struct ry, tmp, tmp2
   Dim As Double t, t1, t2
   Dim As Long i, ex, l, prec
   
   l=Log((NUMBER_OF_DIGITS+9.63)*0.0625)*1.5
   ex=(x.exponent And &h7FFFFFFF)-BIAS-1
   t=x.mantissa[0]+x.mantissa[1]/&h100000000
   t=t/&h10000000
   t1=Log(t)/p
   t2=0.6931471805599453*ex/p
   t1=Exp(t1)
   ry=dbl2fp(t2)
   ry=fpexp(ry,1)
   tmp=dbl2fp(t1)
   ry=fpmul(ry, tmp,1)
   prec=3

   tmp=fpipow(ry,p-1, prec)
   tmp=fpdiv(x, tmp, prec)
   tmp2=fpmul_si(ry, p-1, prec)
   tmp2=fpadd(tmp2, tmp, prec)
   ry=fpdiv_si(tmp2, p, prec)   
   For i=1 To l
      prec=2*prec-1
      tmp=fpipow(ry,p-1, prec)
      tmp=fpdiv(x, tmp, prec)
      tmp2=fpmul_si(ry, p-1, prec)
      tmp2=fpadd(tmp2, tmp, prec)
      ry=fpdiv_si(tmp2, p, prec)
   Next
   Return ry
End Function

Function binomial(Byval n As Long, Byval k As Long) As BigFloat
   Dim As BigFloat c
   Dim As Long i
    If k < 0 Or k > n Then
        Return 0
    End If
    If k = 0 Or k = n Then
        Return 1
    End If
    k = Iif(k<=(n - k),k,(n-k))  ' Take advantage of symmetry
    c = 1
    For i=0 To k-1
        c = c * (n - i) / (i + 1)
    Next
    Return c
End Function

Public Function euler2n(Byval n As Integer) As BigFloat
   Dim As BigFloat a, s1
   Dim As Integer i, k
   a = 0
   For k = 1 To 2 * n + 1 Step 2
      s1 = 0
      For i = 0 To k
         s1 = s1 + (-1)^i * BigFloat(k - 2 * i)^(2 * n + 1) * binomial(k, i)
      Next
      a = a + Sgn((-1)^(k / 2 - 0.5)) * s1 / (2^k) / k
   Next
   Return a
End Function


