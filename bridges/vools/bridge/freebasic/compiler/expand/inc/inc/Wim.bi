'此模块由坏坏小生 QQ 20273541 翻译

#inclib "ntdll"
#inclib "pthread"
#inclib "winpthread"
#inclib "xml2"
#inclib "wim"
#Include Once "crt\win32\stdio.bi"

#define WIMLIB_CHANGE_READONLY_FLAG   &H00000001


#define WIMLIB_CHANGE_GUID   &H00000002

#define WIMLIB_CHANGE_BOOT_INDEX   &H00000004


#define WIMLIB_CHANGE_RPFIX_FLAG   &H00000008

#define WIMLIB_ITERATE_DIR_TREE_FLAG_RECURSIVE   &H00000001

#define WIMLIB_ITERATE_DIR_TREE_FLAG_CHILDREN   &H00000002

#define WIMLIB_ITERATE_DIR_TREE_FLAG_RESOURCES_NEEDED   &H00000004

#define WIMLIB_ADD_FLAG_NTFS   &H00000001

#define WIMLIB_ADD_FLAG_DEREFERENCE   &H00000002

#define WIMLIB_ADD_FLAG_VERBOSE   &H00000004

#define WIMLIB_ADD_FLAG_BOOT   &H00000008

#define WIMLIB_ADD_FLAG_UNIX_DATA   &H00000010

#define WIMLIB_ADD_FLAG_NO_ACLS   &H00000020

#define WIMLIB_ADD_FLAG_STRICT_ACLS   &H00000040

#define WIMLIB_ADD_FLAG_EXCLUDE_VERBOSE   &H00000080

#define WIMLIB_ADD_FLAG_RPFIX   &H00000100

#define WIMLIB_ADD_FLAG_NORPFIX   &H00000200

#define WIMLIB_ADD_FLAG_WINCONFIG   &H00000800

#define WIMLIB_ADD_FLAG_WIMBOOT   &H00001000

#define WIMLIB_ADD_FLAG_NO_REPLACE   &H00002000

#define WIMLIB_ADD_FLAG_TEST_FILE_EXCLUSION   &H00004000

#define WIMLIB_ADD_FLAG_SNAPSHOT   &H00008000

#define WIMLIB_ADD_FLAG_FILE_PATHS_UNNEEDED   &H00010000

#define WIMLIB_DELETE_FLAG_FORCE   &H00000001

#define WIMLIB_DELETE_FLAG_RECURSIVE   &H00000002

#define WIMLIB_EXPORT_FLAG_BOOT   &H00000001

#define WIMLIB_EXPORT_FLAG_NO_NAMES   &H00000002

#define WIMLIB_EXPORT_FLAG_NO_DESCRIPTIONS   &H00000004

#define WIMLIB_EXPORT_FLAG_GIFT   &H00000008

#define WIMLIB_EXPORT_FLAG_WIMBOOT   &H00000010

#define WIMLIB_EXTRACT_FLAG_NTFS   &H00000001

#define WIMLIB_EXTRACT_FLAG_UNIX_DATA   &H00000020

#define WIMLIB_EXTRACT_FLAG_NO_ACLS   &H00000040

#define WIMLIB_EXTRACT_FLAG_STRICT_ACLS   &H00000080

#define WIMLIB_EXTRACT_FLAG_RPFIX   &H00000100

#define WIMLIB_EXTRACT_FLAG_NORPFIX   &H00000200

#define WIMLIB_EXTRACT_FLAG_TO_STDOUT   &H00000400

#define WIMLIB_EXTRACT_FLAG_REPLACE_INVALID_FILENAMES   &H00000800

#define WIMLIB_EXTRACT_FLAG_ALL_CASE_CONFLICTS   &H00001000

#define WIMLIB_EXTRACT_FLAG_STRICT_TIMESTAMPS   &H00002000

#define WIMLIB_EXTRACT_FLAG_STRICT_SHORT_NAMES   &H00004000

#define WIMLIB_EXTRACT_FLAG_STRICT_SYMLINKS   &H00008000

#define WIMLIB_EXTRACT_FLAG_GLOB_PATHS   &H00040000

#define WIMLIB_EXTRACT_FLAG_STRICT_GLOB   &H00080000

#define WIMLIB_EXTRACT_FLAG_NO_ATTRIBUTES   &H00100000

#define WIMLIB_EXTRACT_FLAG_NO_PRESERVE_DIR_STRUCTURE   &H00200000

#define WIMLIB_EXTRACT_FLAG_WIMBOOT   &H00400000

#define WIMLIB_EXTRACT_FLAG_COMPACT_XPRESS4K   &H01000000

#define WIMLIB_EXTRACT_FLAG_COMPACT_LZX   &H08000000

#define WIMLIB_MOUNT_FLAG_READWRITE   &H00000001

#define WIMLIB_MOUNT_FLAG_DEBUG   &H00000002

#define WIMLIB_MOUNT_FLAG_STREAM_INTERFACE_NONE   &H00000004

#define WIMLIB_MOUNT_FLAG_STREAM_INTERFACE_XATTR   &H00000008

#define WIMLIB_MOUNT_FLAG_STREAM_INTERFACE_WINDOWS   &H00000010

#define WIMLIB_MOUNT_FLAG_UNIX_DATA   &H00000020

#define WIMLIB_MOUNT_FLAG_ALLOW_OTHER   &H00000040

#define WIMLIB_OPEN_FLAG_CHECK_INTEGRITY   &H00000001

#define WIMLIB_OPEN_FLAG_ERROR_IF_SPLIT   &H00000002

#define WIMLIB_OPEN_FLAG_WRITE_ACCESS   &H00000004

#define WIMLIB_UNMOUNT_FLAG_CHECK_INTEGRITY   &H00000001

#define WIMLIB_UNMOUNT_FLAG_COMMIT   &H00000002

#define WIMLIB_UNMOUNT_FLAG_REBUILD   &H00000004

#define WIMLIB_UNMOUNT_FLAG_RECOMPRESS   &H00000008

#define WIMLIB_UNMOUNT_FLAG_FORCE   &H00000010

#define WIMLIB_UNMOUNT_FLAG_NEW_IMAGE   &H00000020

#define WIMLIB_WRITE_FLAG_CHECK_INTEGRITY   &H00000001

#define WIMLIB_WRITE_FLAG_NO_CHECK_INTEGRITY   &H00000002

#define WIMLIB_WRITE_FLAG_PIPABLE   &H00000004

#define WIMLIB_WRITE_FLAG_NOT_PIPABLE   &H00000008

#define WIMLIB_WRITE_FLAG_RECOMPRESS   &H00000010

#define WIMLIB_WRITE_FLAG_FSYNC   &H00000020

#define WIMLIB_WRITE_FLAG_REBUILD   &H00000040

#define WIMLIB_WRITE_FLAG_SOFT_DELETE   &H00000080

#define WIMLIB_WRITE_FLAG_IGNORE_READONLY_FLAG   &H00000100

#define WIMLIB_WRITE_FLAG_SKIP_EXTERNAL_WIMS   &H00000200

#define WIMLIB_WRITE_FLAG_STREAMS_OK   &H00000400

#define WIMLIB_WRITE_FLAG_RETAIN_GUID   &H00000800

#define WIMLIB_WRITE_FLAG_SOLID   &H00001000

#define WIMLIB_WRITE_FLAG_SEND_DONE_WITH_FILE_MESSAGES   &H00002000

#define WIMLIB_WRITE_FLAG_NO_SOLID_SORT   &H00004000

#define WIMLIB_WRITE_FLAG_UNSAFE_COMPACT   &H00008000

#define WIMLIB_INIT_FLAG_ASSUME_UTF8   &H00000001

#define WIMLIB_INIT_FLAG_DONT_ACQUIRE_PRIVILEGES   &H00000002


#define WIMLIB_INIT_FLAG_STRICT_CAPTURE_PRIVILEGES   &H00000004

#define WIMLIB_INIT_FLAG_STRICT_APPLY_PRIVILEGES   &H00000008

#define WIMLIB_INIT_FLAG_DEFAULT_CASE_SENSITIVE   &H00000010

#define WIMLIB_INIT_FLAG_DEFAULT_CASE_INSENSITIVE   &H00000020

#define WIMLIB_REF_FLAG_GLOB_ENABLE   &H00000001


#define WIMLIB_REF_FLAG_GLOB_ERR_ON_NOMATCH   &H00000002


#define WIMLIB_NO_IMAGE   0


#define WIMLIB_ALL_IMAGES   -1

#define WIMLIB_GUID_LEN 16


Enum wimlib_compression_type
   
   WIMLIB_COMPRESSION_TYPE_NONE = 0
   WIMLIB_COMPRESSION_TYPE_XPRESS = 1
   WIMLIB_COMPRESSION_TYPE_LZX = 2
   WIMLIB_COMPRESSION_TYPE_LZMS = 3
   
End Enum

Union MPath

wim_target_path As PLONG
symlink_target As PLONG

End Union

Enum statusA
   
   
   WIMLIB_SCAN_DENTRY_OK = 0
   WIMLIB_SCAN_DENTRY_EXCLUDED = 1
   WIMLIB_SCAN_DENTRY_UNSUPPORTED = 2
   WIMLIB_SCAN_DENTRY_FIXED_SYMLINK = 3
   WIMLIB_SCAN_DENTRY_NOT_FIXED_SYMLINK = 4
   
End Enum

Type wimlib_wim_info
    guid(WIMLIB_GUID_LEN) As UByte    '此 WIM 的全局唯一标识符。
	 image_count As ULong     '此 WIM 文件中的图像数。
	 boot_index As ULong      '此 WIM 文件中可启动映像的从 1 开始的索引，如果没有可启动映像，则为 0。
	 wim_version as ULong     '此 WIM 文件中使用的 WIM 文件格式的版本。
	 chunk_size as ULong       '此 WIM 文件中资源的默认压缩块大小。
	 part_number as UShort      '对于拆分 WIM，拆分 WIM 中该部分的从 1 开始的索引；否则 1.
	 total_parts as UShort      '对于拆分 WIM，拆分 WIM 中的部件总数；否则 1.
	 compression_type as ULong   '此 WIM 文件中资源的默认压缩类型，作为wimlib_compression_type常量之一。
	 total_bytes As ULongInt     '此 WIM 文件的大小（以字节为单位），不包括 XML 数据和完整性表。
	 has_integrity_table : 1 As ULong 
	 opened_from_file : 1 As ULong 
	 is_readonly : 1 As ULong 
	 has_rpfix : 1 As ULong 
	 is_marked_readonly : 1 As ULong 
	 spanned : 1 As ULong 
	 write_in_progress : 1 As ULong 
	 metadata_only : 1 As ULong 
	 resource_only : 1 As ULong 
	 pipable : 1 as ULong 
	 reserved_flags : 22 As ULong 
	 reserved(9) As ULong 
End Type




Type wimlib_progress_info_write_streams
   
   total_bytes As ULongInt
   total_streams As ULongInt
   completed_bytes As ULongInt
   completed_streams As ULongInt
   num_threads As ULong
   compression_type As ULong
   total_parts As ULong
   completed_parts As ULong
End Type

Type wimlib_progress_info_scan
   
   source As PLONG
   cur_path As PLONG
   
   status As statusA
   
   
   wimlib_tchar As mpath
   
   'wim_target_path As PLONG
   
   num_dirs_scanned As ULongInt
   num_nondirs_scanned As ULongInt
   num_bytes_scanned As ULongInt
   
End Type

Type wimlib_progress_info_extract
   image As ULong
   extract_flags As ULong
   wimfile_name As PLONG
   image_name As  PLONG
   target As PLONG
   reserved As PLONG
   total_bytes As ULongInt
   completed_bytes As ULongInt
   total_streams As ULong
   completed_streams As ULong
   part_number As ULong
   total_parts As ULong
   GUID(16) As UByte
   current_file_count As ULongInt
   end_file_count As ULongInt
   
End Type

Type wimlib_progress_info_rename
   
   formA As PLONG
   
   ToA As PLONG
   
End Type

Type wimlib_progress_info_update
   
   CommandStr As PLONG
   completed_commands As ULong
   total_commands As ULong
   
End Type

Type wimlib_progress_info_integrity
   
   total_bytes As ULongInt
   completed_bytes As ULongInt
   total_chunks As ULong
   completed_chunks As ULong
   chunk_size As ULong
   filename As PLONG
   
End Type

Type wimlib_progress_info_split
   
   total_bytes As ULongInt
   completed_bytes As ULongInt
   cur_part_number As UINT16
   total_parts As UINT16
   part_name As PLONG
   
End Type

Type wimlib_progress_info_replace
   
   path_in_wim As PLONG
   
End Type

Type wimlib_progress_info_wimboot_exclude
   
   path_in_wim As PLONG
   extraction_path As PLONG
   
End Type

Type wimlib_progress_info_unmount
   
   mountpoint As PLONG
   mounted_wim As PLONG
   mounted_image As ULong
   mount_flags As ULong
   unmount_flags As ULong
   
End Type

Type wimlib_progress_info_done_with_file
   
   path_to_file As PLONG
   
End Type

Type wimlib_progress_info_verify_image
   
   wimfile As PLONG
   total_images As ULong
   current_image As ULong
   
End Type

Type wimlib_progress_info_verify_streams
   
   wimfile As PLONG
   total_streams As ULongInt
   total_bytes As ULongInt
   completed_streams As ULongInt
   completed_bytes As ULongInt
   
End Type

Type wimlib_progress_info_test_file_exclusion
   
   path As PLONG
   will_exclude As BOOL
   
End Type

Type wimlib_progress_info_handle_error
   
   path As PLONG
   error_code As Long
   will_ignore As BOOL
   
End Type






Union wimlib_progress_info

write_streams As wimlib_progress_info_write_streams
scan As wimlib_progress_info_scan
extract As wimlib_progress_info_extract
rename As wimlib_progress_info_rename
update As wimlib_progress_info_update
integrity As wimlib_progress_info_integrity
SplitA As wimlib_progress_info_split
replaceA As wimlib_progress_info_replace
wimboot_exclude As wimlib_progress_info_wimboot_exclude
unmount As wimlib_progress_info_unmount
done_with_file As wimlib_progress_info_done_with_file
verify_image As wimlib_progress_info_verify_image
verify_streams As wimlib_progress_info_verify_streams
test_file_exclusion As wimlib_progress_info_test_file_exclusion
handle_error As wimlib_progress_info_handle_error

End Union



Enum Wimlib_compression_type_code
   
   WIMLIB_COMPRESSION_TYPE_NONE = 0
   
   WIMLIB_COMPRESSION_TYPE_XPRESS = 1
   
   WIMLIB_COMPRESSION_TYPE_LZX = 2
   
   WIMLIB_COMPRESSION_TYPE_LZMS = 3
   
End Enum


Enum wimlib_progress_status
   
   WIMLIB_PROGRESS_STATUS_CONTINUE = 0
   
   WIMLIB_PROGRESS_STATUS_ABORT = 1
   
   
   
End Enum




Enum wimlib_error_code
   WIMLIB_ERR_SUCCESS = 0
   WIMLIB_ERR_ALREADY_LOCKED = 1
   WIMLIB_ERR_DECOMPRESSION = 2
   WIMLIB_ERR_FUSE = 6
   WIMLIB_ERR_GLOB_HAD_NO_MATCHES = 8
   WIMLIB_ERR_IMAGE_COUNT = 10
   WIMLIB_ERR_IMAGE_NAME_COLLISION = 11
   WIMLIB_ERR_INSUFFICIENT_PRIVILEGES = 12
   WIMLIB_ERR_INTEGRITY = 13
   WIMLIB_ERR_INVALID_CAPTURE_CONFIG = 14
   WIMLIB_ERR_INVALID_CHUNK_SIZE = 15
   WIMLIB_ERR_INVALID_COMPRESSION_TYPE = 16
   WIMLIB_ERR_INVALID_HEADER = 17
   WIMLIB_ERR_INVALID_IMAGE = 18
   WIMLIB_ERR_INVALID_INTEGRITY_TABLE = 19
   WIMLIB_ERR_INVALID_LOOKUP_TABLE_ENTRY = 20
   WIMLIB_ERR_INVALID_METADATA_RESOURCE = 21
   WIMLIB_ERR_INVALID_OVERLAY = 23
   WIMLIB_ERR_INVALID_PARAM = 24
   WIMLIB_ERR_INVALID_PART_NUMBER = 25
   WIMLIB_ERR_INVALID_PIPABLE_WIM = 26
   WIMLIB_ERR_INVALID_REPARSE_DATA = 27
   WIMLIB_ERR_INVALID_RESOURCE_HASH = 28
   WIMLIB_ERR_INVALID_UTF16_STRING = 30
   WIMLIB_ERR_INVALID_UTF8_STRING = 31
   WIMLIB_ERR_IS_DIRECTORY = 32
   WIMLIB_ERR_IS_SPLIT_WIM = 33
   WIMLIB_ERR_LINK = 35
   WIMLIB_ERR_METADATA_NOT_FOUND = 36
   WIMLIB_ERR_MKDIR = 37
   WIMLIB_ERR_MQUEUE = 38
   WIMLIB_ERR_NOMEM = 39
   WIMLIB_ERR_NOTDIR = 40
   WIMLIB_ERR_NOTEMPTY = 41
   WIMLIB_ERR_NOT_A_REGULAR_FILE = 42
   WIMLIB_ERR_NOT_A_WIM_FILE = 43
   WIMLIB_ERR_NOT_PIPABLE = 44
   WIMLIB_ERR_NO_FILENAME = 45
   WIMLIB_ERR_NTFS_3G = 46
   WIMLIB_ERR_OPEN = 47
   WIMLIB_ERR_OPENDIR = 48
   WIMLIB_ERR_PATH_DOES_NOT_EXIST = 49
   WIMLIB_ERR_READ = 50
   WIMLIB_ERR_READLINK = 51
   WIMLIB_ERR_RENAME = 52
   WIMLIB_ERR_REPARSE_POINT_FIXUP_FAILED = 54
   WIMLIB_ERR_RESOURCE_NOT_FOUND = 55
   WIMLIB_ERR_RESOURCE_ORDER = 56
   WIMLIB_ERR_SET_ATTRIBUTES = 57
   WIMLIB_ERR_SET_REPARSE_DATA = 58
   WIMLIB_ERR_SET_SECURITY = 59
   WIMLIB_ERR_SET_SHORT_NAME = 60
   WIMLIB_ERR_SET_TIMESTAMPS = 61
   WIMLIB_ERR_SPLIT_INVALID = 62
   WIMLIB_ERR_STAT = 63
   WIMLIB_ERR_UNEXPECTED_END_OF_FILE = 65
   WIMLIB_ERR_UNICODE_STRING_NOT_REPRESENTABLE = 66
   WIMLIB_ERR_UNKNOWN_VERSION = 67
   WIMLIB_ERR_UNSUPPORTED = 68
   WIMLIB_ERR_UNSUPPORTED_FILE = 69
   WIMLIB_ERR_WIM_IS_READONLY = 71
   WIMLIB_ERR_WRITE = 72
   WIMLIB_ERR_XML = 73
   WIMLIB_ERR_WIM_IS_ENCRYPTED = 74
   WIMLIB_ERR_WIMBOOT = 75
   WIMLIB_ERR_ABORTED_BY_PROGRESS = 76
   WIMLIB_ERR_UNKNOWN_PROGRESS_STATUS = 77
   WIMLIB_ERR_MKNOD = 78
   WIMLIB_ERR_MOUNTED_IMAGE_IS_BUSY = 79
   WIMLIB_ERR_NOT_A_MOUNTPOINT = 80
   WIMLIB_ERR_NOT_PERMITTED_TO_UNMOUNT = 81
   WIMLIB_ERR_FVE_LOCKED_VOLUME = 82
   WIMLIB_ERR_UNABLE_TO_READ_CAPTURE_CONFIG = 83
   WIMLIB_ERR_WIM_IS_INCOMPLETE = 84
   WIMLIB_ERR_COMPACTION_NOT_POSSIBLE = 85
   WIMLIB_ERR_IMAGE_HAS_MULTIPLE_REFERENCES = 86
   WIMLIB_ERR_DUPLICATE_EXPORTED_IMAGE = 87
   WIMLIB_ERR_CONCURRENT_MODIFICATION_DETECTED = 88
   WIMLIB_ERR_SNAPSHOT_FAILURE = 89
   WIMLIB_ERR_INVALID_XATTR = 90
   WIMLIB_ERR_SET_XATTR = 91
End Enum
Enum wimlib_progress_msg
   
   WIMLIB_PROGRESS_MSG_EXTRACT_IMAGE_BEGIN = 0
   'info将指向wimlib_progress_info.extract。对于调用wimlib_extract_image()和wimlib_extract_image_from_pipe()，每个映像接收此消息一次。
   
   WIMLIB_PROGRESS_MSG_EXTRACT_TREE_BEGIN = 1
   
   '将提取WIM映像中的一个或多个文件或目录树.info将指向wimlib_progress_info.extract。
   '每个wimlib_extract_paths()和wimlib_extract_pathlist()只接收此消息一次，因为为了优化目的，wimlib将所有路径组合到一个提取操作中。
   
   WIMLIB_PROGRESS_MSG_EXTRACT_FILE_STRUCTURE = 3
   
   '在创建文件和目录时，可以在文件数据提取之前定期发送此消息(不是针对每个文件)。
   'info将指向wimlib_progress_info.extract。特别是，current_file_count和end_file_count成员可以用来跟踪这个提取阶段的进度。
   
   WIMLIB_PROGRESS_MSG_EXTRACT_STREAMS = 4
   
   '目前正在提取文件数据。
   'info将指向wimlib_progress_info.extract。这是跟踪提取操作进度的主要消息。
   
   WIMLIB_PROGRESS_MSG_EXTRACT_SPWM_PART_BEGIN = 5
   
   '开始读取管道上可拆分的WIM的新部分。
   'info将指向wimlib_progress_info.extract。
   
   WIMLIB_PROGRESS_MSG_EXTRACT_METADATA = 6
   
   '在提取文件数据之后，在提取文件和目录元数据时，可能会定期发送此消息(不一定针对每个文件)。
   'info将指向wimlib_progress_info.extract。current_file_count和end_file_count成员可用于跟踪此提取阶段的进度。
   
   WIMLIB_PROGRESS_MSG_EXTRACT_IMAGE_END = 7
   
   'Image已成功提取。
   'info将指向wimlib_progress_info.extract。它与WIMLIB_PROGRESS_MSG_EXTRACT_IMAGE_BEGIN相匹配。
   
   WIMLIB_PROGRESS_MSG_EXTRACT_TREE_END = 8
   
   '文件或目录树已成功提取。
   'info将指向wimlib_progress_info.extract。它与WIMLIB_PROGRESS_MSG_EXTRACT_TREE_BEGIN相匹配。
   
   WIMLIB_PROGRESS_MSG_SCAN_BEGIN = 9
   
   '将扫描目录或NTFS卷以获取元数据。
   'info将指向wimlib_progress_info.scan。此消息在每次调用wimlib_add_image()时接收一次
   '或者在每次捕获源传递给wimlib_add_image_multisource()时接收一次，或者在每次添加命令传递给wimlib_update_image()时接收一次。
   
   WIMLIB_PROGRESS_MSG_SCAN_DENTRY = 10
   
   '已扫描目录或文件。
   'info将指向wimlib_progress_info。扫描，其cur_path成员将有效。只有在指定了WIMLIB_ADD_FLAG_VERBOSE之后，才会发送此消息。
   
   WIMLIB_PROGRESS_MSG_SCAN_END = 11
   
   '目录或NTFS卷已成功扫描。
   'info将指向wimlib_progress_info.scan。这与前面的WIMLIB_PROGRESS_MSG_SCAN_BEGIN消息相匹配
   '可能还包含许多中间的WIMLIB_PROGRESS_MSG_SCAN_DENTRY消息。
   
   WIMLIB_PROGRESS_MSG_WRITE_STREAMS = 12
   
   '文件数据目前正在写入WIM。
   'info将指向wimlib_progress_info.write_streams。在用wimlib_write()、wimlib_overwrite()或wimlib_write_to_fd()编写或附加WIM文件时，可能会多次收到此消息。
   
   WIMLIB_PROGRESS_MSG_WRITE_METADATA_BEGIN = 13
   
   '每个Image的元数据将被写入WIM文件。
   'info失效
   
   WIMLIB_PROGRESS_MSG_WRITE_METADATA_END = 14
   
   '每个图像的元数据已写入WIM文件。
   'info失效。此消息与前面的WIMLIB_PROGRESS_MSG_WRITE_METADATA_BEGIN消息相匹配。
   
   WIMLIB_PROGRESS_MSG_RENAME = 15
   
   'wimlib_overwrite()已经成功地将临时文件重命名为原始WIM文件，从而将更改提交到WIM文件。
   'info将指向wimlib_progress_info.rename。注意 : 如果wimlib_overwrite()选择附加到WIM文件中，则不接收此消息。
   
   WIMLIB_PROGRESS_MSG_VERIFY_INTEGRITY = 16
   
   '正在根据完整性表检查WIM文件的内容。
   'info将指向wimlib_progress_info.integrity。只有在使用WIMLIB_OPEN_FLAG_CHECK_INTEGRITY标志调用wimlib_open_wim_with_progress()时才会接收此消息(可能会多次接收)。
   
   WIMLIB_PROGRESS_MSG_CALC_INTEGRITY = 17
   
   '正在为正在编写的WIM计算一个完整性表。
   'info将指向wimlib_progress_info.integrity。只有在使用WIMLIB_WRITE_FLAG_CHECK_INTEGRITY标志编写WIM文件时才会接收此消息(可能会多次接收)。
   
   WIMLIB_PROGRESS_MSG_SPLIT_BEGIN_PART = 19
   
   'wimlib_split()操作正在进行中，一个新的分割部分即将启动。
   'info将指向wimlib_progress_info.Split。
   
   WIMLIB_PROGRESS_MSG_SPLIT_END_PART = 20
   
   'wimlib_split()操作正在进行中，一个分割部分已经完成。
   'info将指向wimlib_progress_info.Split。
   
   WIMLIB_PROGRESS_MSG_UPDATE_BEGIN_COMMAND = 21
   
   '将要执行一个WIM update命令。
   'info将指向wimlib_progress_info.update。当使用WIMLIB_UPDATE_FLAG_SEND_PROGRESS标志调用wimlib_update_image()时，每个update命令接收此消息一次。
   
   WIMLIB_PROGRESS_MSG_UPDATE_END_COMMAND = 22
   
   '执行了一个WIM update命令。
   'info将指向wimlib_progress_info.update。当使用WIMLIB_UPDATE_FLAG_SEND_PROGRESS标志调用wimlib_update_image()时，每个update命令接收此消息一次。
   
   WIMLIB_PROGRESS_MSG_REPLACE_FILE_IN_WIM = 23
   
   '在没有指定WIMLIB_ADD_FLAG_NO_REPLACE的情况下，使用wimlib_add_add_command替换映像中的文件。
   'info将指向wimlib_progress_info.replace。只有当在add命令中指定WIMLIB_ADD_FLAG_VERBOSE时，才会接收到该命令
   
   WIMLIB_PROGRESS_MSG_WIMBOOT_EXCLUDE = 24
   
   '使用WIMLIB_EXTRACT_FLAG_WIMBOOT提取一个映像，并且通常提取一个文件(不是作为“WIMBoot指针文件”)，因为它匹配WIM映像中配置文件/Windows/System32/WimBootCompress.ini的[PrepopulateList]部分中的模式。
   'info将指向wimlib_progress_info.wimboot_exclude。
   
   WIMLIB_PROGRESS_MSG_UNMOUNT_BEGIN = 25
   
   '开始卸载映像。
   'info将指向wimlib_progress_info.unmount。
   
   WIMLIB_PROGRESS_MSG_DONE_WITH_FILE = 26
   
   'wimlib最后一次使用了文件的数据(如果有多个数据流，则包括所有数据流)。
   'info将指向wimlib_progress_info.done_with_file。只有在提供WIMLIB_WRITE_FLAG_SEND_DONE_WITH_FILE_MESSAGES时才会接收此消息。
   
   
   WIMLIB_PROGRESS_MSG_BEGIN_VERIFY_IMAGE = 27
   
   'wimlib_verify_wim()开始验证image的元数据。
   'info将指向wimlib_progress_info.verify_image。
   
   WIMLIB_PROGRESS_MSG_END_VERIFY_IMAGE = 28
   
   'wimlib_verify_wim()已经验证了Image的元数据。
   'info将指向wimlib_progress_info.verify_image。
   
   WIMLIB_PROGRESS_MSG_VERIFY_STREAMS = 29
   
   'wimlib_verify_wim()正在验证文件数据的完整性。
   'info将指向wimlib_progress_info.verify_streams。
   
   WIMLIB_PROGRESS_MSG_TEST_FILE_EXCLUSION = 30
   
   '正在询问progress函数是否应该从捕获中排除文件。
   'info将指向wimlib_progress_info.test_file_exclusion。这是一条双向消息，允许progress函数在应该排除文件时设置一个标志。
   '只有在使用WIMLIB_ADD_FLAG_TEST_FILE_EXCLUSION标志时才会接收此消息。这种文件排除方法独立于“捕获配置文件”机制。
   
   WIMLIB_PROGRESS_MSG_HANDLE_ERROR = 31
   
   '发生错误，正在询问progress函数是否忽略该错误。
   'info将指向wimlib_progress_info.handle_error。这是一个双向消息。
   '这条消息为应用程序从底层操作系统引起的“意外”错误(即没有库内处理策略的错误)中恢复提供了有限的功能。通常，任何此类错误都会导致库中止当前操作。通过实现此消息的处理程序，应用程序可以选择忽略给定的错误。
   '目前，只有以下类型的错误才会导致此进度消息被发送:
   '目录树扫描错误，例如来自wimlib_add_image()
   '大多数提取错误;目前仅限于该库的Windows构建。
   
End Enum
Extern "C"

Declare Function 	wimlib_add_empty_image(wim As Plong ,ImgName As WString Ptr  ,new_idx_ret As Plong) As Long
' 将空图像附加到WIMStruct。
 
Declare Function  	wimlib_add_image (Wim As PLong, source As WString  ptr , ImgName As WString Ptr  , config_file As WString  Ptr  , add_flags As Long) As Long
 '将图像从磁盘目录树或 NTFS 卷添加到WIMStruct。
 
Declare Function 	wimlib_add_image_multisource (wim As Plong , sources As WString Ptr ,  num_sources As ULong , ImgName As WString Ptr , config_file As WString Ptr ,  add_flags As Long )  As Long 
 '	此函数与wimlib_add_image()等效，只是它允许将多个源组合成单个 WIM 映像。
 
Declare Function  	wimlib_add_tree (wim As Plong  ,  image As Long , fs_source_path as WString Ptr , wim_target_path as WString Ptr , add_flags As Long )    As Long 
 	'在文件或目录树添加fs_source_path在文件系统中的位置wim_target_path的指定范围内image的wim。
 
Declare Function   	wimlib_create_new_wim (CtypeA As Long,  wim_ret As PLong ptr) As Long
 '	创建一个最初不包含图像且不受磁盘文件支持的WIMStruct。 
 
Declare Function   	wimlib_delete_image (wim As Plong ,  image as Long ) As Long 
 	'从WIMStruct 中删除一个图像或所有图像。
 
Declare Function   	wimlib_delete_path ( wim As Plong ,  image As Long , Path as WString Ptr  ,  delete_flags As Long )   As Long 
 '	path从 的指定image中删除wim。 
 
Declare Function   	wimlib_export_image (src_wim As Plong ,  src_image As Long , dest_wim As Plong ,  dest_name As Plong , dest_description As Plong ,  export_flags As Long )  As Long 
 '	将图像或所有图像从WIMStruct 导出到另一个WIMStruct。 
 
Declare Function  	wimlib_extract_image ( wim as Plong ,  image As Long =1 , target As WString  Ptr ,  extract_flags As Long )  As Long 
 	'从WIMStruct 中提取图像或所有图像。
 
Declare Function  	wimlib_extract_image_from_pipe ( pipe_fd As Long , image_num_or_name As Plong , target As Plong ,  extract_flags As Long ) As Long 
 '	从正在发送可管道化 WIM 的管道中提取一个图像。
 
Declare Function  	wimlib_extract_image_from_pipe_with_progress ( pipe_fd As Long ,image_num_or_name as Plong , target As Plong , extract_flags as long ,  progfunc As Any Ptr , progctx as PUlong )   As Long 
 '与wimlib_extract_image_from_pipe()相同，但允许指定进度函数。
 
Declare Function   	wimlib_extract_pathlist (Wim as Plong , image as long , target as Plong , path_list_file as Plong , extract_flags as long )  As Long 
 '	与wimlib_extract_paths()类似，但要从 WIM 图像中提取的路径在 ASCII、UTF-8 或 UTF-16LE 文本文件中指定，path_list_file该文件本身包含要使用的路径列表，每行一个。
 
Declare Function   	wimlib_extract_paths (Wim as Plong , image as long , target as WString Ptr  ,  paths As WString Ptr  , num_paths as ULong , extract_flags as long )  As Long 
 '	从指定的 WIM 映像中提取零个或多个路径（文件或目录树）。
 
Declare Function   	wimlib_extract_xml_data (Wim as PLONG , fp As FILE Ptr )   As Long 
 	'与wimlib_get_xml_data()类似，但 XML 文档将写入指定的标准 C，FILE*而不是在内存缓冲区中检索。
 
Declare Sub   	wimlib_free (Wim as Plong )
 '	释放对WIMStruct的引用。
 
Declare Function  	wimlib_get_compression_type_string ( ctype As Long )   As WString Ptr 
' 	将wimlib_compression_type值转换为字符串。
' 
Declare Function  	wimlib_get_error_string (code As Long )    As WString Ptr 
' 将 wimlib 错误代码转换为描述它的字符串。.
' 
Declare Function  	wimlib_get_image_description ( Wim as Plong , image as long )    As WString Ptr 
' 获取指定图像的描述。
' 
Declare Function  	wimlib_get_image_name ( Wim as Plong , image as long )   As WString Ptr 
' 	获取指定图像的名称。
' 
Declare Function  wimlib_get_image_property ( Wim as Plong , image as long , property_name As WString Ptr )    As WString Ptr 
' 	从 wimlib v1.8.3 开始：从 WIM 的 XML 文档中获取每个图像的属性。
 
Declare Function  	wimlib_get_version ()  As ULong  
' 	将 wimlib 的版本作为 32 位数字返回，其中前 12 位包含主要版本，接下来的 10 位包含次要版本，低 10 位包含补丁版本。
 
Declare Function  	wimlib_get_version_string () As WString Ptr 
 	'从 wimlib v1.13.0 开始：类似于wimlib_get_version()，但返回在构建时设置的完整 PACKAGE_VERSION 字符串。
 
Declare Function  	wimlib_get_wim_info (Wim as Plong , info As wimlib_wim_info Ptr  )    As Long 
 	'获取有关 WIM 文件的基本信息。
 
Declare Function   	wimlib_get_xml_data (wim As PLong,   ByRef buf_ret As UByte Ptr   , bufsize_ret As PUlong) As Long
 '	将 WIM 文件的 XML 文档读入内存缓冲区。
 
Declare Function 	wimlib_global_init ( init_flags As  Long )  As Long 
 	'wimlib 的初始化函数。
 
Declare Sub   	wimlib_global_cleanup ()
 	'wimlib 的清理功能。
 
Declare Function  	wimlib_image_name_in_use ( Wim as Plong ,   ImgName As WString Ptr  )  As BOOL 
 '	确定某个映像名称是否已被 WIM 中的某个映像使用。
 
Declare Function  	wimlib_iterate_dir_tree (Wim as Plong , image as long ,  path As WString Ptr  ,  flags As Long ,  cb As Long , user_ctx As Any Ptr )   As Long 
 '	遍历 WIM 映像中的文件或目录树。
 
Declare Function  	wimlib_iterate_lookup_table (Wim as Plong , flags as long , cb as long , user_ctx As Any  Ptr )  As Long 
 '	遍历WIMStruct的 blob 查找表。 
 
Declare Function 	wimlib_join (swms As Plong ,  num_swms As Long ,   output_path As WString Ptr  ,  swm_open_flags As Long ,  wim_write_flags As Long )   As Long 
 '	将拆分的 WIM 加入独立的（单部分）WIM。
 
Declare Function 	wimlib_join_with_progress ( swms As Plong ,  num_swms As Long , output_path As WString Ptr ,  swm_open_flags as Long ,  wim_write_flags As Long , progfunc as any ptr , progctx As Any Ptr )  As Long 
' 	与wimlib_join()相同，但允许指定进度函数。
' 
Declare Function 	wimlib_mount_image (Wim as Plong , image as long , Mountdir As WString  Ptr ,  mount_flags As Long ,  staging_dir as WString Ptr )  As Long 
' 	将 WIM 文件中的映像挂载到只读或读写目录上。
' 
Declare Function 	wimlib_open_wim ( wim_file As WString Ptr ,  open_flags As Long ,  wim_ret As PLONG  Ptr ) As Long 
' 	打开 WIM 文件并为其创建WIMStruct。
' 
Declare Function  	wimlib_open_wim_with_progress ( wim_file As WString Ptr , open_flags as long , wim_ret as PLONG  ptr , progfunc as any ptr , progctx As Any ptr) As Long 
' 	与wimlib_open_wim()相同，但允许指定进度函数和进度上下文。
' 
Declare Function  wimlib_overwrite (Wim as Plong , write_flags as long ,  num_threads As Long )  As Long 
' 	将WIMStruct提交到磁盘，更新其后备文件。
' 
Declare sub 	wimlib_print_available_images ( Wim as Plong , image as long )
' 	（已弃用）打印有关 WIM 中包含的一个图像或所有图像的信息。
' 
Declare sub 	wimlib_print_header ( Wim as Plong )
' 	打印 WIM 文件的标题（仅用于调试）。
' 
Declare Function	wimlib_reference_resource_files (Wim as Plong ,   resource_wimfiles_or_globs As WString Ptr ,  count as Long , ref_flags as long , open_flags as long )  As Long 
' 	参考来自其他 WIM 文件或拆分 WIM 部件的文件数据。
' 
Declare Function	wimlib_reference_resources (Wim as Plong , resource_wims As PLONG  Ptr ,  num_resource_wims As Long , ref_flags as long )  As Long 
' 	与wimlib_reference_resource_files()类似，但在较低级别运行，调用者必须为每个引用的文件本身打开WIMStruct。
' 
Declare Function	wimlib_reference_template_image (Wim as Plong ,  new_image As Long, template_wim As PLONG  ,  template_image As Long , flags as long )  As Long 
' 	声明新添加的图像与之前的图像大致相同，但在稍后的时间点捕获，可能在中间时间进行了一些修改。
' 
Declare sub 	wimlib_register_progress_function (Wim as Plong , progfunc as any ptr , progctx as ULong  Ptr )
' 	使用WIMStruct注册进度函数。
' 
Declare Function	 	wimlib_rename_path (Wim as Plong , image as long ,source_path As WString Ptr , dest_path As WString Ptr )  As Long 
' 重命名source_path到dest_path指定image的wim。
' 
Declare Function	wimlib_resolve_image (Wim as Plong ,  image_name_or_num As WString Ptr )   As Long 
' 	将指定 WIM 中图像名称或编号的字符串转换为图像编号。
' 
Declare Function	wimlib_set_error_file ( fp as FILE Ptr ) As Long 
' 	设置库将打印错误和警告消息的文件。
' 
Declare Function	wimlib_set_error_file_by_name ( path As WString Ptr )  As Long 
' 	设置库将打印错误和警告消息的文件的路径。
' 
Declare Function	wimlib_set_image_descripton (Wim as Plong , image as long ,  description As WString Ptr ) As Long 
' 更改 WIM 映像的描述。
' 
Declare Function	wimlib_set_image_flags (Wim as Plong , image as long ,  flags As WString Ptr )  As Long 
' 	更改 WIM XML 文档中 <FLAGS> 元素中存储的内容（通常类似于“Core”或“Ultimate”）。
' 
Declare Function	wimlib_set_image_name (Wim as Plong , image as long ,  Wname As WString Ptr )  As Long 
' 	更改 WIM 映像的名称。 
' 
Declare Function	wimlib_set_image_property (Wim as Plong , image as long ,  property_name As WString Ptr ,  property_value As WString Ptr )   As Long 
' 	从 wimlib v1.8.3 开始：从 WIM 的 XML 文档中添加、修改或删除每个图像的属性。
' 
Declare Function	wimlib_set_memory_allocator (ByVal malloc_func As Any Ptr ,ByVal free_func As Any Ptr ,ByVal realloc_func As Any Ptr)   As Long 
' 	设置 wimlib 用于分配和释放内存的函数。
' 
Declare Function	wimlib_set_output_chunk_size (Wim as Plong ,  chunk_size As ULong )  As Long 
' 	设置WIMStruct的输出压缩块大小。
' 
Declare Function	wimlib_set_output_pack_chunk_size (Wim as Plong ,  chunk_size as ULong )   As Long 
' 类似于wimlib_set_output_chunk_size()，但设置块大小以写入固体资源。
' 
Declare Function 	wimlib_set_output_compression_type (Wim as Plong , ctype as Long )  As Long 
' 	设置WIMStruct的输出压缩类型。
' 
Declare Function	wimlib_set_output_pack_compression_type (Wim as Plong ,  ctype As Long )  As Long 
' 类似于wimlib_set_output_compression_type()，但设置压缩类型以写入固体资源。
' 
Declare Function 	wimlib_set_print_errors ( show_messages as BOOL )   As Long 
' 设置 wimlib 是否可以将错误和警告消息打印到错误文件中，默认为标准错误。
' 
Declare Function 	wimlib_set_wim_info (Wim as Plong ,  info as wimlib_wim_info Ptr , which As Long )  As Long 
' 	设置 WIM 的基本信息。
' 
Declare Function 	wimlib_split (Wim as Plong ,   swm_name As WString Ptr ,  part_size As ULongInt , write_flags as long ) As Long 
' 	 将 WIM 拆分为多个部分。
' 
Declare Function  	wimlib_verify_wim (Wim as PLONG  ,  verify_flags As Long )   As Long 
' 	对 WIM 文件执行验证检查。
' 
Declare Function 	wimlib_unmount_image ( Wdir as WString Ptr  ,  unmount_flags As Long )  As Long 
' 卸载使用wimlib_mount_image()挂载的 WIM 映像。
' 
Declare Function 	wimlib_unmount_image_with_progress ( Wdir As WString Ptr , unmount_flags As Long , progfunc as any ptr , progctx as Any Ptr ) As Long 
' 	与wimlib_unmount_image()相同，但允许指定进度函数。
' 
Declare Function  	wimlib_update_image (Wim as Plong , image as long , cmds as any ptr ,  num_cmds As size_t,  update_flags as Long )  As Long 
' 	通过添加、删除和/或重命名文件或目录来更新 WIM 映像。
' 
Declare Function  	wimlib_write (Wim as Plong ,  path As WString Ptr , image as long , write_flags as long ,  num_threads as Long ) As Long 
' 将WIMStruct 保留到新的磁盘 WIM 文件中。
' 
Declare Function 	wimlib_write_to_fd (Wim as Plong ,  fd as Long , image as long , write_flags as long ,  num_threads as Long ) As Long 
' 	同wimlib_write（） ，而是直接写入WIM一个文件描述符，这要是写是通过提供一个特殊的pipable WIM格式做了不一定是可搜索WIMLIB_WRITE_FLAG_PIPABLE中write_flags。
' 
Declare Function 	wimlib_set_default_compression_level ( ctype As Long ,  compression_level As Long )  As Long 
' 	为指定的压缩类型设置默认压缩级别。
' 
Declare Function wimlib_get_compressor_needed_memory (ctype As Long ,  max_block_size as ULong ,  compression_level as Long ) As ULongInt 
' 	返回使用wimlib_create_compressor()为指定的压缩类型、最大块大小和压缩级别分配压缩器所需的近似字节数。 
' 
Declare Function 	wimlib_create_compressor (  ctype As Long ,  max_block_size As ULong , compression_level As Long , compressor_ret as Plong Ptr )  As Long 
' 	使用指定的参数为指定的压缩类型分配压缩器。
' 
Declare Function	wimlib_compress (uncompressed_data as Any Ptr ,  uncompressed_size As ULong , compressed_data As Any Ptr ,  compressed_size_avail as ULong , compressor as Plong )  As ULong 
' 	压缩数据缓冲区。
' 
Declare sub	wimlib_free_compressor (compressor As Plong )
' 	释放先前使用wimlib_create_compressor()分配的压缩器。
' 
Declare Function 	wimlib_create_decompressor ( ctype As Long ,  max_block_size As ULong , decompressor_ret As Plong Ptr )As Long 
' 	为指定的压缩类型分配一个解压缩器。
' 
Declare Function wimlib_decompress (compressed_data As any ptr,  compressed_size As ULong , uncompressed_data As Any Ptr ,  uncompressed_size As ULong , decompressor As Plong ) As Long 
' 	解压缩数据缓冲区。
' 
Declare sub wimlib_free_decompressor (decompressor As Plong )
' 	释放先前使用wimlib_create_decompressor()分配的解压缩器。

End Extern



'回调函数写法
'Function imagex_progress_func cdecl(msg As wimlib_progress_msg ,ByRef info As wimlib_progress_info ,ByVal _ignored_context As PVOID) As wimlib_progress_status
'   
'End Function
