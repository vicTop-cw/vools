


Type PROCESS_BASIC_INFORMATION_32
	ExitStatus As UInteger							' 退出状态
	PebBaseAddress As PVOID						' Peb地址 [Process Environment Block]
	AffinityMask As UInteger						' 进程关联掩码
	BasePriority As UInteger						' 进程的优先级
	UniqueProcessId As UInteger					' 进程ID
	InheritedFromUniqueProcessId As UInteger		' 父进程ID
End Type

Type PROCESS_BASIC_INFORMATION_64
	ExitStatus As ULongInt						' 退出状态
	PebBaseAddress As ULongInt					' Peb地址 [Process Environment Block]
	AffinityMask As ULongInt					' 进程关联掩码
	BasePriority As ULongInt					' 进程的优先级
	UniqueProcessId As ULongInt					' 进程ID
	InheritedFromUniqueProcessId As ULongInt	' 父进程ID
End Type

Type UNICODE_STRING_32		' 8 Byte
	Length As UShort
	MaximumLength As UShort
	Buffer As UInteger
End Type

Type UNICODE_STRING_64		' 16 Byte
	Length As UShort
	MaximumLength As UShort
	Buffer As ULongInt
End Type

Type LIST_ENTRY_32
	Flink As DWORD
	Blink As DWORD
End Type

Type LIST_ENTRY_64
	Flink As DWORD
	Blink As DWORD
End Type

Type CURDIR_32
	DosPath As UNICODE_STRING_32
	Handle As UInteger
End Type

Type CURDIR_64
	DosPath As UNICODE_STRING_64
	Handle As UINT64
End Type

Type RTL_DRIVE_LETTER_CURDIR_32
	Flags As WORD
	Length As WORD
	TimeStamp As ULong
	DosPath As UNICODE_STRING_32
End Type

Type RTL_DRIVE_LETTER_CURDIR_64
	Flags As WORD
	Length As WORD
	TimeStamp As ULong
	DosPath As UNICODE_STRING_64
End Type

Type PROCESS_PARAMETERS_32
	MaximumLength As ULong
	Length As ULong
	Flags As ULong
	DebugFlags As ULong
	ConsoleHandle As UInteger
	ConsoleFlags As ULong
	StandardInput As UInteger
	StandardOutput As UInteger
	StandardError As UInteger
	CurrentDirectory As CURDIR_32
	DllPath As UNICODE_STRING_32
	ImagePathName As UNICODE_STRING_32
	CommandLine As UNICODE_STRING_32
	Environment As UINT32
	StartingX As ULong
	StartingY As ULong
	CountX As ULong
	CountY As ULong
	CountCharsX As ULong
	CountCharsY As ULong
	FillAttribute As ULong
	WindowFlags As ULong
	ShowWindowFlags As ULong
	WinTitle As UNICODE_STRING_32
	DesktopInfo As UNICODE_STRING_32
	ShellInfo As UNICODE_STRING_32
	RuntimeData As UNICODE_STRING_32
	CurrentDirectores(1 To 32) As RTL_DRIVE_LETTER_CURDIR_32
	EnvironmentSize As ULong
End Type

Type PROCESS_PARAMETERS_64
	MaximumLength As ULong
	Length As ULong
	Flags As ULong
	DebugFlags As ULong
	ConsoleHandle As UINT64
	ConsoleFlags As ULong
	StandardInput As UINT64
	StandardOutput As UINT64
	StandardError As UINT64
	CurrentDirectory As CURDIR_64
	DllPath As UNICODE_STRING_64
	ImagePathName As UNICODE_STRING_64
	CommandLine As UNICODE_STRING_64
	Environment As UINT64
	StartingX As ULong
	StartingY As ULong
	CountX As ULong
	CountY As ULong
	CountCharsX As ULong
	CountCharsY As ULong
	FillAttribute As ULong
	WindowFlags As ULong
	ShowWindowFlags As ULong
	WinTitle As UNICODE_STRING_64
	DesktopInfo As UNICODE_STRING_64
	ShellInfo As UNICODE_STRING_64
	RuntimeData As UNICODE_STRING_64
	CurrentDirectores(1 To 32) As RTL_DRIVE_LETTER_CURDIR_64
	EnvironmentSize As ULong
End Type

Type PROCESS_ENVIRONMENT_BLOCK_32
	Union
		Type
			InheritedAddressSpace As UByte
			ReadImageFileExecOptions As UByte
			BeingDebugged As UByte
			BitField As UByte
		End Type
		dummy01 As UInteger
	End Union
	Mutant As UInteger
	ImageBaseAddress As UInteger
	Ldr As UInteger
	ProcessParameters As PROCESS_PARAMETERS_32 Ptr
	SubSystemData As UInteger
	ProcessHeap As UInteger
	FastPebLock As UInteger
	AtlThunkSListPtr As UInteger
	IFEOKey As UInteger
	CrossProcessFlags As UInteger
	UserSharedInfoPtr As UInteger
	SystemReserved As DWORD
	AtlThunkSListPtr32 As DWORD
	ApiSetMap As UInteger
	TlsExpansionCounter As UInteger
	TlsBitmap As UInteger
	TlsBitmapBits(1 To 2) As DWORD
	ReadOnlySharedMemoryBase As UInteger
	HotpatchInformation As UInteger
	ReadOnlyStaticServerData As UInteger
	AnsiCodePageData As UInteger
	OemCodePageData As UInteger
	UnicodeCaseTableData As UInteger
	NumberOfProcessors As DWORD
	Union
		NtGlobalFlag As DWORD
		dummy02 As DWORD64
	End Union
	CriticalSectionTimeout As LARGE_INTEGER
	HeapSegmentReserve As UInteger
	HeapSegmentCommit As UInteger
	HeapDeCommitTotalFreeThreshold As UInteger
	HeapDeCommitFreeBlockThreshold As UInteger
	NumberOfHeaps As DWORD
	MaximumNumberOfHeaps As DWORD
	ProcessHeaps As UInteger
	GdiSharedHandleTable As UInteger
	ProcessStarterHelper As UInteger
	GdiDCAttributeList As UInteger
	LoaderLock As UInteger
	OSMajorVersion As DWORD
	OSMinorVersion As DWORD
	OSBuildNumber As WORD
	OSCSDVersion As WORD
	OSPlatformId As DWORD
	ImageSubsystem As DWORD
	ImageSubsystemMajorVersion As DWORD
	ImageSubsystemMinorVersion As UInteger
	ActiveProcessAffinityMask As UInteger
	GdiHandleBuffer(1 To 34) As UInteger
	PostProcessInitRoutine As UInteger
	TlsExpansionBitmap As UInteger
	TlsExpansionBitmapBits(1 To 32) As DWORD
	SessionId As UInteger
	AppCompatFlags As ULARGE_INTEGER
	AppCompatFlagsUser As ULARGE_INTEGER
	pShimData As UInteger
	AppCompatInfo As UInteger
	CSDVersion As UNICODE_STRING_32
	ActivationContextData As UInteger
	ProcessAssemblyStorageMap As UInteger
	SystemDefaultActivationContextData As UInteger
	SystemAssemblyStorageMap As UInteger
	MinimumStackCommit As UInteger
	FlsCallback As UInteger
	FlsListHead As LIST_ENTRY_32
	FlsBitmap As UInteger
	FlsBitmapBits(1 To 4) As DWORD
	FlsHighIndex As UInteger
	WerRegistrationData As UInteger
	WerShipAssertPtr As UInteger
	pContextData As UInteger
	pImageHeaderHash As UInteger
	TracingFlags As UInteger
	CsrServerReadOnlySharedMemoryBase As UInteger
End Type

Type PROCESS_ENVIRONMENT_BLOCK_64
	Union
		Type
			InheritedAddressSpace As UByte
			ReadImageFileExecOptions As UByte
			BeingDebugged As UByte
			BitField As UByte
		End Type
		dummy01 As DWORD64
	End Union
	Mutant As DWORD64
	ImageBaseAddress As DWORD64
	Ldr As DWORD64
	ProcessParameters As DWORD64
	SubSystemData As DWORD64
	ProcessHeap As DWORD64
	FastPebLock As DWORD64
	AtlThunkSListPtr As DWORD64
	IFEOKey As DWORD64
	CrossProcessFlags As DWORD64
	UserSharedInfoPtr As DWORD64
	SystemReserved As DWORD
	AtlThunkSListPtr32 As DWORD
	ApiSetMap As DWORD64
	TlsExpansionCounter As DWORD64
	TlsBitmap As DWORD64
	TlsBitmapBits1 As DWORD
	TlsBitmapBits2 As DWORD
	ReadOnlySharedMemoryBase As DWORD64
	HotpatchInformation As DWORD64
	ReadOnlyStaticServerData As DWORD64
	AnsiCodePageData As DWORD64
	OemCodePageData As DWORD64
	UnicodeCaseTableData As DWORD64
	NumberOfProcessors As DWORD
	Union
		NtGlobalFlag As DWORD
		dummy02 As DWORD
	End Union
	CriticalSectionTimeout As LARGE_INTEGER
	HeapSegmentReserve As DWORD64
	HeapSegmentCommit As DWORD64
	HeapDeCommitTotalFreeThreshold As DWORD64
	HeapDeCommitFreeBlockThreshold As DWORD64
	NumberOfHeaps As DWORD
	MaximumNumberOfHeaps As DWORD
	ProcessHeaps As DWORD64
	GdiSharedHandleTable As DWORD64
	ProcessStarterHelper As DWORD64
	GdiDCAttributeList As DWORD64
	LoaderLock As DWORD64
	OSMajorVersion As DWORD
	OSMinorVersion As DWORD
	OSBuildNumber As WORD
	OSCSDVersion As WORD
	OSPlatformId As DWORD
	ImageSubsystem As DWORD
	ImageSubsystemMajorVersion As DWORD
	ImageSubsystemMinorVersion As DWORD64
	ActiveProcessAffinityMask As DWORD64
	GdiHandleBuffer(1 To 30) As DWORD64
	PostProcessInitRoutine As DWORD64
	TlsExpansionBitmap As DWORD64
	TlsExpansionBitmapBits(1 To 32) As DWORD
	SessionId As DWORD64
	AppCompatFlags As ULARGE_INTEGER
	AppCompatFlagsUser As ULARGE_INTEGER
	pShimData As DWORD64
	AppCompatInfo As DWORD64
	CSDVersion As UNICODE_STRING_64
	ActivationContextData As DWORD64
	ProcessAssemblyStorageMap As DWORD64
	SystemDefaultActivationContextData As DWORD64
	SystemAssemblyStorageMap As DWORD64
	MinimumStackCommit As DWORD64
	FlsCallback As DWORD64
	FlsListHead As LIST_ENTRY_64
	FlsBitmap As DWORD64
	FlsBitmapBits(1 To 4) As DWORD
	FlsHighIndex As DWORD64
	WerRegistrationData As DWORD64
	WerShipAssertPtr As DWORD64
	pContextData As DWORD64
	pImageHeaderHash As DWORD64
	TracingFlags As DWORD64
	CsrServerReadOnlySharedMemoryBase As DWORD64
End Type

#Define ProcessBasicInformation 0
#Define NT_SUCCESS(Status) (Status >= 0)

Declare Function NtQueryInformationProcess Lib "ntdll" Alias "NtQueryInformationProcess"(ProcessHandle as HANDLE, ProcessInformationClass as UINT, ProcessInformation as PVOID, ProcessInformationLength as ULong, ReturnLength as PULONG) as Integer
Declare Function NtReadVirtualMemory Lib "ntdll" Alias "NtReadVirtualMemory"(ProcessHandle as HANDLE, BaseAddress as PVOID, Buffer as PVOID, NumberOfBytesToRead as SIZE_T, NumberOfBytesReaded as PUINT) as Integer

