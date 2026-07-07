#include "win\iphlpapi.bi"
Declare Function IcmpCreateFile Lib "icmp.dll" Alias "IcmpCreateFile"()As HANDLE
Declare Function IcmpCloseHandle Lib "icmp.dll" Alias "IcmpCloseHandle"(Hdr As HANDLE) As Integer
Declare Function IcmpSendEcho Lib "icmp.dll" Alias "IcmpSendEcho"(IcmpHandle As HANDLE, DestAddress As Integer, RequestData As Any Ptr, RequestSize As Integer, RequestOptns As Any Ptr, ReplyBuffer As Any Ptr, ReplySize As Integer, TimeOut As Integer) As Integer

