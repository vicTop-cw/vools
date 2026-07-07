


#Include Once "win/wininet.bi"



#Define G_HTTP_POST_HEAD !"Content-Type: application/x-www-form-urlencoded\r\n"



Dim Shared G_HTTP_Agent  As ZString * MAX_PATH = !"Mozilla/4.0 (compatible; MSIE 6.0; Windows NT 5.0)\0"
Dim Shared G_HTTP_Head  As ZString * 4096 = !"\0"
Dim Shared G_HTTP_Accept As ZString * MAX_PATH = !"*/*\0"
Dim Shared G_HTTP_Ver  As ZString * 32 = !"HTTP/1.1\0"
Dim Shared G_HTTP_Block  As UInteger = 4096



Extern "Windows-MS"
 
 Sub Http_SetAgent(NewVal As ZString Ptr) Export
  G_HTTP_Agent = *NewVal
 End Sub
 
 Sub Http_SetHead(NewVal As ZString Ptr) Export
  G_HTTP_Head = *NewVal
 End Sub
 
 Sub Http_SetAccept(NewVal As ZString Ptr) Export
  G_HTTP_Accept = *NewVal
 End Sub
 
 Sub Http_SetVer(NewVal As ZString Ptr) Export
  G_HTTP_Ver = *NewVal
 End Sub
 
 Sub Http_SetBlock(NewVal As UInteger) Export
  G_HTTP_Block = NewVal
 End Sub
 
Function Http_Get(host As ZString Ptr ,path As ZString Ptr ,ref As ZString Ptr ,user As ZString Ptr ,pwd As ZString Ptr) As ZString Ptr Export
   Dim hInet As HANDLE = InternetOpen(@G_HTTP_Agent ,INTERNET_OPEN_TYPE_DIRECT ,NULL ,NULL ,0)
   If hInet Then
      Dim hConn As HANDLE = InternetConnect(hInet ,host ,INTERNET_DEFAULT_HTTP_PORT ,user ,pwd ,INTERNET_SERVICE_HTTP ,0 ,0)
      If hConn Then
         Dim hRequ As HANDLE = HttpOpenRequest(hConn ,"GET" ,path ,@G_HTTP_Ver ,ref ,Cast(LPCSTR Ptr ,@G_HTTP_Accept) ,INTERNET_FLAG_CACHE_IF_NET_FAIL ,0)
         If hRequ Then
            Dim bRequ As Integer = HttpSendRequest(hRequ ,@G_HTTP_Head , -1 ,NULL ,0)
            If bRequ Then
               Dim pBuff As ZString Ptr = malloc(G_HTTP_Block)
               Dim bRead As UInteger
               AutoFreeBuffer.FreeMemory()
               While InternetReadFile(hRequ ,pBuff ,G_HTTP_Block ,@bRead) AndAlso (bRead > 0)
                  AutoFreeBuffer.PutData(pBuff ,bRead)
               Wend
               free(pBuff)
            Else
               Return @xRtl.xywh_library_xrtl_memory_snull
            EndIf
         Else
            Return @xRtl.xywh_library_xrtl_memory_snull
         EndIf
      Else
         Return @xRtl.xywh_library_xrtl_memory_snull
      EndIf
      InternetCloseHandle(hInet)
   Else
      Return @xRtl.xywh_library_xrtl_memory_snull
   EndIf
   Return AutoFreeBuffer.BufferMemory
End Function
 
Function Http_GetFile(file As ZString Ptr ,host As ZString Ptr ,path As ZString Ptr ,ref As ZString Ptr ,user As ZString Ptr ,pwd As ZString Ptr) As Integer Export
   If Http_Get(host ,path ,ref ,user ,pwd) Then
      Return xRtl.File.Write(file ,AutoFreeBuffer.BufferMemory ,0 ,AutoFreeBuffer.BufferUseLen)
   EndIf
End Function

Function Http_Post(host As ZString Ptr ,path As ZString Ptr ,param As ZString Ptr ,ref As ZString Ptr ,user As ZString Ptr ,pwd As ZString Ptr) As ZString Ptr Export
   Dim hInet As HANDLE = InternetOpen(@G_HTTP_Agent ,INTERNET_OPEN_TYPE_DIRECT ,NULL ,NULL ,0)
   If hInet Then
      Dim hConn As HANDLE = InternetConnect(hInet ,host ,INTERNET_DEFAULT_HTTP_PORT ,user ,pwd ,INTERNET_SERVICE_HTTP ,0 ,0)
      If hConn Then
         Dim hRequ As HANDLE = HttpOpenRequest(hConn ,"POST" ,path ,@G_HTTP_Ver ,ref ,Cast(LPCSTR Ptr ,@G_HTTP_Accept) ,INTERNET_FLAG_CACHE_IF_NET_FAIL ,0)
         If hRequ Then
            Dim bRequ As Integer = HttpSendRequest(hRequ ,G_HTTP_POST_HEAD & G_HTTP_Head , -1 ,Param ,strlen(Param))
            If bRequ Then
               Dim pBuff As ZString Ptr = malloc(G_HTTP_Block)
               Dim bRead As UInteger
               AutoFreeBuffer.FreeMemory()
               While InternetReadFile(hRequ ,pBuff ,G_HTTP_Block ,@bRead) AndAlso (bRead > 0)
                  AutoFreeBuffer.PutData(pBuff ,bRead)
               Wend
               free(pBuff)
            Else
               Return @xRtl.xywh_library_xrtl_memory_snull
            EndIf
         Else
            Return @xRtl.xywh_library_xrtl_memory_snull
         EndIf
      Else
         Return @xRtl.xywh_library_xrtl_memory_snull
      EndIf
      InternetCloseHandle(hInet)
   Else
      Return @xRtl.xywh_library_xrtl_memory_snull
   EndIf
   Return AutoFreeBuffer.BufferMemory
End Function
 
Function Http_PostFile(file As ZString Ptr ,host As ZString Ptr ,path As ZString Ptr ,param As ZString Ptr ,ref As ZString Ptr ,user As ZString Ptr ,pwd As ZString Ptr) As Integer Export
   If Http_Post(host ,path ,param ,ref ,user ,pwd) Then
      Return xRtl.FILE.Write(FILE ,AutoFreeBuffer.BufferMemory ,0 ,AutoFreeBuffer.BufferUseLen)
   EndIf
End Function
 
End Extern
