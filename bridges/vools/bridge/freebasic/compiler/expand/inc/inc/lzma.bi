#Include once "crt.bi"
#inclib "LZMA"



#define SZ_OK 0

#define SZ_ERROR_DATA 1
#define SZ_ERROR_MEM 2
#define SZ_ERROR_CRC 3
#define SZ_ERROR_UNSUPPORTED 4
#define SZ_ERROR_PARAM 5
#define SZ_ERROR_INPUT_EOF 6
#define SZ_ERROR_OUTPUT_EOF 7
#define SZ_ERROR_READ 8
#define SZ_ERROR_WRITE 9
#define SZ_ERROR_PROGRESS 10
#define SZ_ERROR_FAIL 11
#define SZ_ERROR_THREAD 12

#define SZ_ERROR_ARCHIVE 16
#define SZ_ERROR_NO_ARCHIVE 17



#define LZMA_PROPS_SIZE 5

Extern "C"

/'
RAM 要求 LZMA:
  用于压缩:   (dictSize * 11.5 + 6 MB) + state_size
  用于减压: dictSize + state_size
    state_size = (4 + (1.5 << (lc + lp))) KB
    by default (lc=3, LP=0), state_size = 16 KB.

LZMA 性能 (5 bytes) format
    Offset SIZE  描述
      0     1    lc, lp and pb in encoded form.
      1     4    dictSize (little endian).
'/

/'
LzmaCompress
------------

outPropsSize -
     In:  指向outProps缓冲区大小的指针; *outPropsSize = LZMA_PROPS_SIZE = 5.
     Out: 指向outProps缓冲区中写入属性大小的指针; *outPropsSize = LZMA_PROPS_SIZE = 5.

  LZMA 编码器将使用任何参数的默认值, if it is
  -1  for any from: level, loc, lp, pb, fb, numThreads
   0  for dictSize
  
level - compression level: 0 <= level <= 9;

  level dictSize algo  fb
    0:    16 KB   0    32
    1:    64 KB   0    32
    2:   256 KB   0    32
    3:     1 MB   0    32
    4:     4 MB   0    32
    5:    16 MB   1    32
    6:    32 MB   1    32
    7+:   64 MB   1    64
 
  The default value for "level" is 5.

  algo = 0 means fast method
  algo = 1 means normal method

dictSize - 字典大小(以字节为单位) 最大值为
        128 MB = (1 << 27) bytes for 32-bit version
          1 GB = (1 << 30) bytes for 64-bit version
     默认值为 16 MB = (1 << 24) bytes.
     It's recommended to use the dictionary that is larger than 4 KB and
     that can be calculated as (1 << N) or (3 << N) sizes.

lc - 文字上下文位数（以前字面值的高位）).
     It can be in the range from 0 to 8. The default value is 3.
     Sometimes lc=4 gives the gain for big files.

lp - 文字位数（文字当前位置的低位）。
     It can be in the range from 0 to 4. The default value is 0.
     The lp switch is intended for periodical data when the period is equal to 2^lp.
     For example, for 32-bit (4 bytes) periodical data you can use lp=2. Often it's
     better to set lc=0, if you change lp switch.

pb - 位数（当前位置的低位）。
     It can be in the range from 0 to 4. The default value is 2.
     The pb switch is intended for periodical data when the period is equal 2^pb.

fb - 字大小（快字节数）。
     It can be in the range from 5 to 273. The default value is 32.
     Usually, a big number gives a little bit better compression ratio and
     slower compression process.

numThreads - The number of thereads. 1 or 2. The default value is 2.
     Fast mode (algo = 0) can use only 1 thread.

Out:
  destLen  - processed output size
Returns:
  SZ_OK               - OK
  SZ_ERROR_MEM        - 内存分配错误
  SZ_ERROR_PARAM      - 参数不正确
  SZ_ERROR_OUTPUT_EOF - 输出缓冲区溢出
  SZ_ERROR_THREAD     - 多线程功能中的错误（仅适用于Mt版本）
'/



/'
 dest     目标内存
 destLen    目标内存大小[压缩后的]
 src    待压缩内存
 srcLen    压缩数据大小
 outProps   指针缓冲区
 outPropsSize 指针缓冲大小[固定为:LZMA_PROPS_SIZE]
 level     压缩级别[0-9,越大压缩率越高,默认为5]
 dictSize   字典大小
 numThreads  线程数量
'/
Declare Function LzmaCompress(ByVal dest As UByte Ptr,ByRef destLen As size_t,ByVal src As Const UByte Ptr,ByVal srcLen As size_t,ByVal outProps As UByte Ptr,_
        ByRef outPropsSize As size_t, _           ' outPropsSize must be = 5 
                ByVal level As Integer = -1,_             ' 0 <= level <= 9, default = 5 
                ByVal dictSize As UInteger = 0, _         ' default = (1 << 24) 
                ByVal lc As Integer = -1, _               ' 0 <= lc <= 8, default = 3 
                ByVal LP As Integer = -1, _               ' 0 <= lp <= 4, default = 0 
                ByVal pb As Integer = -1, _               ' 0 <= pb <= 4, default = 2  
                byval fb as integer = -1, _               ' 5 <= fb <= 273, default = 32 
                byval numThreads as integer = -1  _       ' 1 or 2, default = 2
                ) As Integer


/'
LzmaUncompress
--------------
In:
  dest     - output data
  destLen  - output data size
  src      - input data
  srcLen   - input data size
Out:
  destLen  - 处理输出大小
  srcLen   - 处理输入大小
Returns:
  SZ_OK                - OK
  SZ_ERROR_DATA        - 数据错误
  SZ_ERROR_MEM         - 内存分配错误
  SZ_ERROR_UNSUPPORTED - 不支持的属性
  SZ_ERROR_INPUT_EOF   - 它在输入缓冲区（src）中需要更多字节
'/

Declare Function LzmaUncompress(ByVal dest As UByte Ptr,ByRef destLen As size_t,ByVal src As Const UByte Ptr,ByRef srcLen As size_t,ByVal props As Const UByte Ptr,ByVal propsSize As size_t) As Integer

end Extern



Type Lzma_FileHdr Field = 1
 FileSize As ULong '压缩后文件大小
 CompLevel As Byte             ' 压缩级别
 LzmaProp(0 To LZMA_PROPS_SIZE-1) As Byte ' Props
End Type





