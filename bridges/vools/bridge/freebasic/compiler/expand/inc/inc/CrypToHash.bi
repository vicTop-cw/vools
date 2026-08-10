/' written by drizz <1of00@gmx.net> '/
#Ifndef __cryptohash_bi__
#define __cryptohash_bi__
#inclib "cryptohash"
Extern "Windows"
' CIPHERS
' =======
Declare Sub DESSetKey Alias "DESSetKey" (ByVal pKey As Byte Ptr)
Declare Sub DESSetKeyEnc Alias "DESSetKeyEnc" (ByVal pKey As Byte Ptr)
Declare Sub DESSetKeyDec Alias "DESSetKeyDec" (ByVal pKey As Byte Ptr)
Declare Sub DESEncrypt Alias "DESEncrypt" (ByVal pBlockIn As Byte Ptr, ByVal pBlockOut As Byte Ptr)
Declare Sub DESDecrypt Alias "DESDecrypt" (ByVal pBlockIn As Byte Ptr, ByVal pBlockOut As Byte Ptr)
Declare Sub RC2Init Alias "RC2Init" (ByVal pKey As Byte Ptr, ByVal dwKeyLen As DWORD)
declare Sub RC2Encrypt alias "RC2Encrypt" (byval pBlockIn as BYTE ptr, byval pBlockOut as BYTE ptr)
declare Sub RC2Decrypt alias "RC2Decrypt" (byval pBlockIn as BYTE ptr, byval pBlockOut as BYTE ptr)
declare Sub RC4Init alias "RC4Init" (byval pKey as BYTE ptr, byval dwKeyLen as DWORD)
declare Sub RC4Encrypt alias "RC4Encrypt" (byval pBlock as BYTE ptr, byval dwBlockLen as DWORD)
#define RC4Decrypt RC4Encrypt
Declare Sub RC5Init Alias "RC5Init" (ByVal pKey As Byte Ptr)
declare Sub RC5Encrypt alias "RC5Encrypt" (byval pBlockIn as BYTE ptr, byval pBlockOut as BYTE ptr)
declare Sub RC5Decrypt alias "RC5Decrypt" (byval pBlockIn as BYTE ptr, byval pBlockOut as BYTE ptr)
declare Sub RC6Init alias "RC6Init" (byval pKey as BYTE ptr, byval dwKeyLen as DWORD)
declare Sub RC6Encrypt alias "RC6Encrypt" (byval pBlockIn as BYTE ptr, byval pBlockOut as BYTE ptr)
declare Sub RC6Decrypt alias "RC6Decrypt" (byval pBlockIn as BYTE ptr, byval pBlockOut as BYTE ptr)
declare Sub XTEAInit alias "XTEAInit" (byval pKey as BYTE ptr, byval dwRounds as DWORD)
declare Sub XTEAEncrypt alias "XTEAEncrypt" (byval pBlockIn as BYTE ptr, byval pBlockOut as BYTE ptr)
declare Sub XTEADecrypt alias "XTEADecrypt" (byval pBlockIn as BYTE ptr, byval pBlockOut as BYTE ptr)
declare Sub RijndaelInit alias "RijndaelInit" (byval pKey as BYTE ptr, byval dwKeyLen as DWORD)
declare Sub RijndaelEncrypt alias "RijndaelEncrypt" (byval pBlockIn as BYTE ptr, byval pBlockOut as BYTE ptr)
declare Sub RijndaelDecrypt alias "RijndaelDecrypt" (byval pBlockIn as BYTE ptr, byval pBlockOut as BYTE ptr)
declare Sub ThreeWayInit alias "ThreeWayInit" (byval pKey as BYTE ptr)
declare Sub ThreeWayEncrypt alias "ThreeWayEncrypt" (byval pBlockIn as BYTE ptr, byval pBlockOut as BYTE ptr)
declare Sub ThreeWayDecrypt alias "ThreeWayDecrypt" (byval pBlockIn as BYTE ptr, byval pBlockOut as BYTE ptr)
declare Sub TEAInit alias "TEAInit" (byval pKey as BYTE ptr)
declare Sub TEAEncrypt alias "TEAEncrypt" (byval pBlockIn as BYTE ptr, byval pBlockOut as BYTE ptr)
declare Sub TEADecrypt alias "TEADecrypt" (byval pBlockIn as BYTE ptr, byval pBlockOut as BYTE ptr)
declare Sub BlowfishInit alias "BlowfishInit" (byval pKey as BYTE ptr, byval dwKeyLen as DWORD)
declare Sub BlowfishEncrypt alias "BlowfishEncrypt" (byval pBlockIn as BYTE ptr, byval pBlockOut as BYTE ptr)
declare Sub BlowfishDecrypt alias "BlowfishDecrypt" (byval pBlockIn as BYTE ptr, byval pBlockOut as BYTE ptr)

' CHECKSUMS
' =========

#define INIT_CRC32 0
#define INIT_CRC16 0
#define INIT_ADLER32 1
Declare Function CRC32 Alias "CRC32" (ByVal lpBuffer As Byte Ptr, ByVal dwBufLen As DWORD, ByVal dwCRC As DWORD) As DWORD ' init dwCRC = 0
declare Function RCRC32 alias "RCRC32" (byval pData as BYTE ptr, byval dwDataLen as DWORD, byval dwOffset as DWORD, byval dwWantCrc as DWORD) As DWORD ' reverse CRC32
declare Function CRC16 alias "CRC16" (byval lpBuffer as BYTE ptr, byval dwBufLen as DWORD, byval dwCRC as DWORD) As DWORD ' init dwCRC = 0
Declare Function Adler32 Alias "Adler32" (ByVal lpBuffer As Byte Ptr, ByVal dwBufLen As DWORD, ByVal dwAdler As DWORD) As DWORD ' init dwAdler = 1

' HASHES
' ======

declare Function MD5Init alias "MD5Init" () As Byte Ptr
declare Sub MD5Update alias "MD5Update" ( byval lpBuffer As Byte ptr, byval dwBufLen As DWORD)
declare Function MD5Final alias "MD5Final" () As Byte Ptr
#define MD5_DIGESTSIZE (128/8)
Declare Function MD4Init alias "MD4Init" () As Byte Ptr
declare Sub MD4Update alias "MD4Update" (byval lpBuffer as BYTE ptr, byval dwBufLen as DWORD)
declare Function MD4Final alias "MD4Final" () As Byte Ptr
#define MD4_DIGESTSIZE (128/8)
declare Function MD2Init alias "MD2Init" () As Byte Ptr
declare Sub MD2Update alias "MD2Update" (byval as DWORD, byval as DWORD)
declare Function MD2Final alias "MD2Final" () As Byte Ptr
#define MD2_DIGESTSIZE (128/8)
Declare Function RMD128Init alias "RMD128Init" () As Byte Ptr
declare Sub RMD128Update alias "RMD128Update" (byval lpBuffer as BYTE ptr, byval dwBufLen as DWORD)
declare Function RMD128Final alias "RMD128Final" () As Byte Ptr
#define RMD128_DIGESTSIZE (128/8)
Declare Function RMD160Init alias "RMD160Init" () As Byte Ptr
declare Sub RMD160Update alias "RMD160Update" (byval lpBuffer as BYTE ptr, byval dwBufLen as DWORD)
declare Function RMD160Final alias "RMD160Final" () As Byte Ptr
#define RMD160_DIGESTSIZE (160/8)
Declare Function RMD256Init alias "RMD256Init" () As Byte Ptr
Declare Sub RMD256Update alias "RMD256Update" (byval lpBuffer as BYTE ptr, byval dwBufLen as DWORD)
declare Function RMD256Final alias "RMD256Final" () As Byte Ptr
#define RMD256_DIGESTSIZE (256/8)
Declare Function RMD320Init alias "RMD320Init" () As Byte Ptr
declare Sub RMD320Update alias "RMD320Update" (byval lpBuffer as BYTE ptr, byval dwBufLen as DWORD)
declare Function RMD320Final alias "RMD320Final" () As Byte Ptr
#define RMD320_DIGESTSIZE (320/8)
Declare Function SHA0Init alias "SHA0Init" () As Byte Ptr
declare Sub SHA0Update alias "SHA0Update" (byval lpBuffer as BYTE ptr, byval dwBufLen as DWORD)
declare Function SHA0Final alias "SHA0Final" () As Byte Ptr
#define SHA0_DIGESTSIZE (160/8)
Declare Function SHA1Init alias "SHA1Init" () As Byte Ptr
declare Sub SHA1Update alias "SHA1Update" (byval lpBuffer as BYTE ptr, byval dwBufLen as DWORD)
declare Function SHA1Final alias "SHA1Final" () As Byte Ptr
#define SHA1_DIGESTSIZE (160/8)
Declare Function SHA256Init alias "SHA256Init" () As Byte Ptr
declare Sub SHA256Update alias "SHA256Update" (byval lpBuffer as BYTE ptr, byval dwBufLen as DWORD)
declare Function SHA256Final alias "SHA256Final" () As Byte Ptr
#define SHA256_DIGESTSIZE (256/8)
Declare Function SHA384Init alias "SHA384Init" () As Byte Ptr
declare Sub SHA384Update alias "SHA384Update" (byval lpBuffer as BYTE ptr, byval dwBufLen as DWORD)
declare Function SHA384Final alias "SHA384Final" () As Byte Ptr
#define SHA384_DIGESTSIZE (384/8)
Declare Function SHA512Init alias "SHA512Init" () As Byte Ptr
declare Sub SHA512Update alias "SHA512Update" (byval lpBuffer as BYTE ptr, byval dwBufLen as DWORD)
declare Function SHA512Final alias "SHA512Final" () As Byte Ptr
#define SHA512_DIGESTSIZE (512/8)
Declare Function WhirlpoolInit alias "WhirlpoolInit" () As Byte Ptr
declare Sub WhirlpoolUpdate alias "WhirlpoolUpdate" (byval lpBuffer as BYTE ptr, byval dwBufLen as DWORD)
declare Function WhirlpoolFinal alias "WhirlpoolFinal" () As Byte Ptr
#define WHIRLPOOL_DIGESTSIZE (512/8)
Declare Function TigerInit alias "TigerInit" () As Byte Ptr
declare Sub TigerUpdate alias "TigerUpdate" (byval lpBuffer as BYTE ptr, byval dwBufLen as DWORD)
declare Function TigerFinal alias "TigerFinal" () As Byte Ptr
#define TIGER_DIGESTSIZE (192/8)
Declare Function HavalInit alias "HavalInit" (ByVal DigestSizeBits As DWORD,ByVal Passes As DWORD) As Byte Ptr ' variable digest & passes !!!
declare Sub HavalUpdate alias "HavalUpdate" (byval lpBuffer as BYTE ptr, byval dwBufLen as DWORD)
declare Function HavalFinal alias "HavalFinal" () As Byte Ptr


' TEXT UTILS
' ==========

declare function HexEncoder alias "HexEncoder" ( ByVal pBuff As Byte Ptr,ByVAL dwLen As DWORD,ByVal pOutBuff As Byte Ptr) As DWORD ' sizeof pOutBuff must be (dwLen)*2+2
declare Function Base64Encode alias "Base64Encode" ( ByVal pInputData As Byte Ptr,ByVal dwDataLen As DWORD,ByVal pOutputStr As Byte Ptr) As DWORD ' sizeof pOutputStr must be (dwLen)*4/3
declare Function Base64Decode alias "Base64Decode" ( ByVal pInputStr As Byte Ptr,ByVal pOutputData As Byte Ptr) As DWORD

End Extern
#EndIf

#Ifdef xywhCoreFile
Function CRC32_File(FilePath As ZString Ptr) As Integer
 Dim FileHdr As HANDLE
 Dim RAM As Any Ptr
 Dim As Integer FileSize,RetInt
 FileHdr = GetOpenFile(FilePath)
 If FileHdr Then
  FileSize = FileLen_h(FileHdr)
  If FileSize Then
   RAM = Allocate(FileSize)
   GetFile_h(FileHdr,RAM,0,FileSize)
   RetInt = CRC32(RAM,FileSize,INIT_CRC32)
   CloseHandle(FileHdr)
   DeAllocate(RAM)
   CRC32_File = RetInt
  EndIf
 EndIf
End Function
#EndIf