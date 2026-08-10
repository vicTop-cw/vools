#include Once "zlib.bi"
#inclib "minizip"

Extern "C"
'解压
Type unzFile As PVOID
Type tm_zip_unz
   tm_sec  As Long
   tm_min  As Long
   tm_hour As Long
   tm_mday As Long
   tm_mon  As Long
   tm_year As Long
End Type
Type unz_global_info
   number_entry As Integer
   size_comment As Long
End Type
Type unz_file_info
   version        As Long
   version_needed As Long
   flag           As Long
   compression_method As Long
   dosDate As ULong
   crc     As Long
   compressed_size   As Integer
   uncompressed_size As Integer
   size_filename     As Long
   size_file_extra   As Long
   size_file_comment As Long
   disk_num_start    As Long
   internal_fa       As Long
   external_fa       As Long
   tmu_date          As tm_zip_unz
   disk_offset       As Integer
   #ifdef __FB_64BIT__
      size_file_extra_internal As Long
   #endif
End Type
#ifdef __FB_64BIT__
   Declare Function unzOpen Alias "unzOpen64"(ByVal path As PSTR) As unzFile
   Declare Function unzGetGlobalInfo Alias "unzGetGlobalInfo64"(ByVal file As unzFile, ByVal pglobal_info As unz_global_info Ptr) As Long
   Declare Function unzGetCurrentFileInfo Alias "unzGetCurrentFileInfo64"(ByVal file As unzFile, ByVal pfile_info As unz_file_info Ptr, ByVal szFileName As LPSTR, ByVal fileNameBufferSize As Long, ByRef extraField As Long, ByVal extraFieldBufferSize As Long, ByVal szComment As LPSTR, ByVal commentBufferSize As Long) As Long
#else
   Declare Function unzOpen(ByVal path As PSTR) As unzFile
   Declare Function unzGetGlobalInfo(ByVal file As unzFile, ByVal pglobal_info As unz_global_info Ptr) As Long
   Declare Function unzGetCurrentFileInfo(ByVal file As unzFile, ByVal pfile_info As unz_file_info Ptr, ByVal szFileName As LPSTR, ByVal fileNameBufferSize As Long, ByRef extraField As Long, ByVal extraFieldBufferSize As Long, ByVal szComment As LPSTR, ByVal commentBufferSize As Long) As Long
#endif
Declare Function unzGoToNextFile(ByVal file As unzFile)    As Long
Declare Function unzOpenCurrentFile(ByVal file As unzFile) As Long
Declare Function unzReadCurrentFile(ByVal file As unzFile, ByVal sbuf As PVOID, ByVal slen As Long) As Long
Declare Function unzOpenCurrentFilePassword(ByVal file As unzFile, ByVal password As LPSTR) As Long
Declare Function unzCloseCurrentFile(ByVal file As unzFile) As Long
Declare Function unzClose(ByVal file As unzFile) As Long

'压缩
Type zipFile As PVOID
Type zip_fileinfo
   tmz_date As tm_zip_unz
   As ULong dosDate, internal_fa, external_fa
End Type
Declare Function zipOpen(ByVal pathname As PCSTR, ByVal Append As Long) As zipFile
Declare Function zipOpenNewFileInZip(ByVal file As zipFile, ByVal filename As PCSTR, ByVal zipfi As zip_fileinfo Ptr, ByVal extrafield_local As LPCVOID, ByVal size_extrafield_local As ULong, ByVal extrafield_global As LPCVOID, ByVal size_extrafield_global As ULong, ByVal comment As PCSTR, ByVal method As Long, ByVal level As Long) As zipFile
Declare Function zipOpenNewFileInZip3(ByVal file As zipFile, ByVal filename As PCSTR, ByVal zipfi As zip_fileinfo Ptr, ByVal extrafield_local As LPCVOID, ByVal size_extrafield_local As ULong, ByVal extrafield_global As LPCVOID, ByVal size_extrafield_global As ULong, ByVal comment As PCSTR, ByVal method As Long, ByVal level As Long, ByVal raw As Long, ByVal windowBits As Long, ByVal memLevel As Long, ByVal strategy As Long, ByVal password As LPSTR, ByVal crcForCrypting As ULong) As Long
Declare Function zipWriteInFileInZip(ByVal file As zipFile, ByVal buf As LPCVOID, ByVal Len As ULong) As Long
Declare Function zipCloseFileInZip(ByVal file As zipFile) As Long
Declare Function zipClose(ByVal file As zipFile, ByVal global_comment As PCSTR) As Long
End Extern

Sub AddFileToZip(ByVal zf As Any Ptr, ByVal fileNameInZip As PCSTR, ByVal srcFile As PSTR, ByVal pwd As String) '添加文件到zip文件，用于内部调用(zip文件结构, zip内部路径, 外部路径) Zip函数内部调用
   Dim zi        As zip_fileinfo '初始化写入zip的文件信息
   Dim file_name As String = *fileNameInZip 'zip中的文件名
   If (GetFileAttributesA(srcFile) And FILE_ATTRIBUTE_DIRECTORY) = FILE_ATTRIBUTE_DIRECTORY Then file_name &= "\" '为空则加入空目录
   Dim File As HANDLE = CreateFileA(srcFile, GENERIC_READ, FILE_SHARE_READ, NULL, OPEN_EXISTING, FILE_FLAG_BACKUP_SEMANTICS, NULL) '打开文件(FILE_FLAG_BACKUP_SEMANTICS可打开目录)
   If File = INVALID_HANDLE_VALUE Then
      zipCloseFileInZip(zf) '关闭zip文件
   Else
      '读取文件时间
      Dim As FILETIME CreationTime, LastAccessTime, LastWriteTime, localt
      GetFileTime(File, @CreationTime, @LastAccessTime, @LastWriteTime) '获取文件时间
      Dim st As SYSTEMTIME
      FileTimeToLocalFileTime(@LastWriteTime, @localt) '将文件时间转换成本地文件时间(标准时间+时区时间)
      FileTimeToSystemTime(@localt, @st) '将本地文件时间转换为本地系统时间
      With zi.tmz_date ' 将系统时间给zip时间结构赋值
         .tm_year = st.wYear
         .tm_mon  = st.wMonth -1 'zip时间结构的月份是0-11，而非1-12，故赋值时先-1
         .tm_mday = st.wDay
         .tm_hour = st.wHour
         .tm_min  = st.wMinute
         .tm_sec  = st.wSecond
      End With
      '读取文件属性
      zi.external_fa = GetFileAttributesA(srcFile)
   End If
   'crc32信息(有密码时必用，传统是PKWARE不安全，现代压缩软件都是AES)
   Dim As ULong crc, nLen, bSize
   If (GetFileAttributesA(srcFile) And FILE_ATTRIBUTE_DIRECTORY) <> FILE_ATTRIBUTE_DIRECTORY Then
      Dim f As HANDLE = CreateFileA(srcFile, GENERIC_READ, FILE_SHARE_READ, NULL, OPEN_EXISTING, NULL, NULL)
      If f <> INVALID_HANDLE_VALUE Then
         nLen = GetFileSize(f, NULL)
         Dim buff As UByte Ptr = malloc(nLen)
         ReadFile(f, buff, nLen, @bSize, NULL)
         CloseHandle(f)
         crc = crc32(0, buff, nLen)
         free(buff)
      End If
   End If
   '在zip文件中创建新文件(zi包含文件时间属性)
   zipOpenNewFileInZip3(zf, file_name, @zi, NULL, 0, NULL, 0, NULL, Z_DEFLATED, Z_DEFAULT_COMPRESSION, 0, -15, 8, Z_DEFAULT_STRATEGY, pwd, crc)
   '读入源文件并写入zip文件
   Dim buf As String * 102400
   While ReadFile(File, @buf, 102400, @nLen, NULL) '返回实际读取字节数给nLen
      If nLen = 0 Then Exit While
      zipWriteInFileInZip(zf, @buf, nLen) '将数据写入zip
   Wend
   CloseHandle(File)
   zipCloseFileInZip(zf) '关闭zip文件
End Sub
'递归添加子目录到zip文件
Sub FilesInDirToZip(ByVal zf As Any Ptr, ByVal path As String, ByVal parentDir As String, ByVal pwd As String) '递归添加子目录到zip文件，用于内部调用(zip句柄, zip内部路径, 外部路径)
   Dim szPath As String
   Dim fd     As WIN32_FIND_DATAA
   Dim file   As HANDLE = FindFirstFileA(parentDir & "\*.*", @fd) '查找文件
   If file <> INVALID_HANDLE_VALUE Then
      Do
         If fd.cFileName = "." Or fd.cFileName = ".." Then Continue Do '过滤当前目录和上级目录
         szPath = parentDir & "\" & fd.cFileName '生成在zip文件中的相对路径
         AddFileToZip(zf, path & "\" & fd.cFileName, szPath, pwd) '添加文件|目录到zip文件中
         If fd.dwFileAttributes = FILE_ATTRIBUTE_DIRECTORY Then '如果是目录
            FilesInDirToZip(zf, path & "\" & fd.cFileName, szPath, pwd) '递归
            Continue Do
         End If
      Loop While FindNextFileA(file, @fd) '遍历下一个文件
      FindClose(file) '关闭文件查找
   End If
End Sub


