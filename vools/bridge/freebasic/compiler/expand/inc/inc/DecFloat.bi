'修改备注：取消 Print 和 End()
'          min 的宏
'删除没用的全局变量和后面代码使用，这些是用于测试的。
'    Dim Shared As Long fp_print_exp=0
'    Dim Shared As Long fp_print_fix=0
'    Dim Shared As Long fp_print_precision=28
'删除 多个全局变量 pi ，使用函数生成
'修正 fpfix_rndu 默认长度时，ex = places 没执行，导致 toString toString_fix 输出大于0时没小数
'======================================================
#ifndef NUMBER_OF_DIGITS
   Const NUMBER_OF_DIGITS = 128
#endif

#if (NUMBER_OF_DIGITS Mod 8) <> 0
   Const NUM_DIGITS = (NUMBER_OF_DIGITS \ 8 + 1) * 8
#else
   Const NUM_DIGITS = NUMBER_OF_DIGITS
#endif
Const NUM_DIGITS2 = NUM_DIGITS -2
Const NUM_DWORDS  = NUM_DIGITS \ 8
#define float_BIAS             1073741824 '2 ^ 30
 'Print NUMBER_OF_DIGITS,NUM_DIGITS2,NUM_DWORDS
' Error definitions

#define DIVZ_ERR        1                    'Divide by zero
#define EXPO_ERR        2                    'Exponent overflow error
#define EXPU_ERR        3                    'Exponent underflow error

Type decfloat_struct
   Declare Constructor()
   Declare Constructor(Byref rhs As decfloat_struct)
   Declare Destructor()
   Declare Operator Let(Byref rhs As decfloat_struct)
   As Short sign    '符号，正负
   As Ulong exponent
   As ULong Ptr mantissa
end type

Constructor decfloat_struct ( )
   if this.mantissa<>0 then
      'Print "pointer is not 0"
      'End (1)
      Return
   end if
   this.mantissa=callocate((NUM_DWORDS +1), 4)
   If This.mantissa=0 Then
      'Print "unable to allocate memory"
      'End(4)
      Return
   end if
   this.sign=0
   this.exponent=0
End Constructor

Constructor decfloat_struct ( Byref rhs As decfloat_struct )
   If This.mantissa<>0 Then
      'print "pointer is not 0"
      'End(1)
      Return
   end if
   this.mantissa=callocate((NUM_DWORDS +1), 4)
   if this.mantissa=0 then
      'Print "unable to allocate memory"
      'End(4)
      Return
   End If
   this.sign=rhs.sign
   this.exponent=rhs.exponent
   for i as long=0 to NUM_DWORDS
      this.mantissa[i]=rhs.mantissa[i]
   next
end Constructor

Operator decfloat_struct.let ( Byref rhs As decfloat_struct )
   this.sign=rhs.sign
   this.exponent=rhs.exponent
   for i as long=0 to NUM_DWORDS
      this.mantissa[i]=rhs.mantissa[i]
   next
End Operator

Destructor decfloat_struct ( )
   If This.mantissa=0 Then
      'Print "unable to de-allocate memory"
      'End(-4)
      Return
   else
      deallocate(this.mantissa)
   End If
   this.mantissa=0
End Destructor

Declare Function pi_brent_salamin (ByVal digits As ULong = NUMBER_OF_DIGITS) As decfloat_struct
declare function fpdiv_si(byref num As decfloat_struct, byval den As Long, byval dwords as long=NUM_DWORDS) As decfloat_struct
declare function fpadd(Byref x As decfloat_struct, Byref y As decfloat_struct, byval dwords as long=NUM_DWORDS) As decfloat_struct
Declare Function str2fp(ByVal value As String ) As decfloat_struct

Type decfloat
    Declare Constructor ( )
    Declare Constructor ( Byval rhs As Long )
    Declare Constructor ( Byval rhs As Longint )
    Declare Constructor ( Byval rhs As Integer )
    Declare Constructor ( Byval rhs As Double )
    Declare Constructor ( Byref rhs As String )
    Declare Constructor ( Byref rhs As decfloat )
    Declare Destructor ( )
    
    Declare Operator Let ( ByVal rhs As Long )
    Declare Operator Let ( ByVal rhs As LongInt )
    Declare Operator Let ( ByVal rhs As Integer )
    Declare Operator Let ( ByVal rhs As Double )
    Declare Operator Let ( ByRef rhs As String )
    Declare Operator Let ( ByRef rhs As decfloat )
    Declare Operator Cast ( ) As String
    Declare Operator Cast ( ) As Long
    Declare Operator Cast ( ) As Double
    
    '----------------------------------------------
    Declare Operator += (Byref rhs As decfloat)
    Declare Operator += (Byval rhs As Longint)
    Declare Operator += (Byval rhs As Double)
    Declare Operator += (Byref rhs As String)
    Declare Operator -= (Byref rhs As decfloat)
    Declare Operator -= (Byval rhs As Longint)
    Declare Operator -= (Byval rhs As Double)
    Declare Operator -= (Byref rhs As String)
    Declare Operator *= (Byref rhs As decfloat)
    Declare Operator *= (Byval rhs As Longint)
    Declare Operator *= (Byval rhs As Double)
    Declare Operator *= (Byref rhs As String)
    Declare Operator /= (Byref rhs As decfloat)
    Declare Operator /= (ByVal rhs As LongInt)
    Declare Operator /= (Byval rhs As Double)
    Declare Operator /= (Byval rhs As Single)
    Declare Operator /= (ByRef rhs As String)

    ' For Next Implicit step = +1
    Declare Operator For ( )
    Declare Operator Step( )
    Declare Operator Next( ByRef end_cond As decfloat ) As Integer
    ' For Next Exlicit step
    Declare Operator For ( ByRef stp As decfloat )
    Declare Operator Step( ByRef stp As decfloat )
    Declare Operator Next( ByRef end_cond As decfloat, ByRef step_var As decfloat ) As Integer
    '----------------------------------------------
    Declare Function toString( ByVal places As Long=NUM_DIGITS2 ) As String
    Declare Function toString_exp( ByVal places As Long=NUM_DIGITS2 ) As String
    Declare Function toString_fix( ByVal places As Long=NUM_DIGITS2 ) As String
    Declare Function toLong ( ) As Long
    Declare Function toDouble ( ) As Double
    Declare Function toLongint ( ) As LongInt

   dec_num As decfloat_struct

End Type



'#if 1
'Scope
'   Dim As String s
'   s+="3.141592653589793238462643383279502884197169399375"
'   s+="10582097494459230781640628620899862803482534211706"
'   s+="79821480865132823066470938446095505822317253594081"
'   s+="28481117450284102701938521105559644622948954930381"
'   s+="96442881097566593344612847564823378678316527120190"
'   s+="91456485669234603486104543266482133936072602491412"
'   s+="73724587006606315588174881520920962829254091715364"
'   s+="36789259036001133053054882046652138414695194151160"
'   s+="94330572703657595919530921861173819326117931051185"
'   s+="48074462379962749567351885752724891227938183011949"
'   s+="12983367336244065664308602139494639522473719070217"
'   s+="98609437027705392171762931767523846748184676694051"
'   s+="32000568127145263560827785771342757789609173637178"
'   s+="72146844090122495343014654958537105079227968925892"
'   s+="35420199561121290219608640344181598136297747713099"
'   s+="60518707211349999998372978049951059731732816096318"
'   s+="59502445945534690830264252230825334468503526193118"
'   s+="81710100031378387528865875332083814206171776691473"
'   s+="03598253490428755468731159562863882353787593751957"
'   s+="78185778053217122680661300192787661119590921642019"
'   s+="89380952572010654858632788659361533818279682303019"
'   s+="52035301852968995773622599413891249721775283479131"
'   s+="51557485724245415069595082953311686172785588907509"
'   s+="83817546374649393192550604009277016711390098488240"
'   s+="12858361603563707660104710181942955596198946767837"
'   s+="44944825537977472684710404753464620804668425906949"
'   s+="12933136770289891521047521620569660240580381501935"
'   s+="11253382430035587640247496473263914199272604269922"
'   s+="79678235478163600934172164121992458631503028618297"
'   s+="45557067498385054945885869269956909272107975093029"
'   s+="55321165344987202755960236480665499119881834797753"
'   s+="56636980742654252786255181841757467289097777279380"
'   s+="00816470600161452491921732172147723501414419735685"
'   s+="48161361157352552133475741849468438523323907394143"
'   s+="33454776241686251898356948556209921922218427255025"
'   s+="42568876717904946016534668049886272327917860857843"
'   s+="83827967976681454100953883786360950680064225125205"
'   s+="11739298489608412848862694560424196528502221066118"
'   s+="63067442786220391949450471237137869609563643719172"
'   s+="87467764657573962413890865832645995813390478027590"
'   s+="09946576407895126946839835259570982582262052248940"
'   s+="77267194782684826014769909026401363944374553050682"
'   s+="03496252451749399651431429809190659250937221696461"
'   s+="51570985838741059788595977297549893016175392846813"
'   s+="82686838689427741559918559252459539594310499725246"
'   s+="80845987273644695848653836736222626099124608051243"
'   s+="88439045124413654976278079771569143599770012961608"
'   s+="94416948685558484063534220722258284886481584560285"
'   s+="06016842739452267467678895252138522549954666727823"
'   s+="98645659611635488623057745649803559363456817432411"
'   s+="25150760694794510965960940252288797108931456691368"
'   s+="67228748940560101503308617928680920874760917824938"
'   s+="58900971490967598526136554978189312978482168299894"
'   s+="87226588048575640142704775551323796414515237462343"
'   s+="64542858444795265867821051141354735739523113427166"
'   s+="10213596953623144295248493718711014576540359027993"
'   s+="44037420073105785390621983874478084784896833214457"
'   s+="13868751943506430218453191048481005370614680674919"
'   s+="27819119793995206141966342875444064374512371819217"
'   s+="99983910159195618146751426912397489409071864942319"
'   s+="61567945208095146550225231603881930142093762137855"
'   s+="95663893778708303906979207734672218256259966150142"
'   s+="15030680384477345492026054146659252014974428507325"
'   s+="18666002132434088190710486331734649651453905796268"
'   s+="56100550810665879699816357473638405257145910289706"
'   s+="41401109712062804390397595156771577004203378699360"
'   s+="07230558763176359421873125147120532928191826186125"
'   s+="86732157919841484882916447060957527069572209175671"
'   s+="16722910981690915280173506712748583222871835209353"
'   s+="96572512108357915136988209144421006751033467110314"
'   s+="12671113699086585163983150197016515116851714376576"
'   s+="18351556508849099898599823873455283316355076479185"
'   s+="35893226185489632132933089857064204675259070915481"
'   s+="41654985946163718027098199430992448895757128289059"
'   s+="23233260972997120844335732654893823911932597463667"
'   s+="30583604142813883032038249037589852437441702913276"
'   s+="56180937734440307074692112019130203303801976211011"
'   s+="00449293215160842444859637669838952286847831235526"
'   s+="58213144957685726243344189303968642624341077322697"
'   s+="80280731891544110104468232527162010526522721116603"
'   s+="96665573092547110557853763466820653109896526918620"
'   s+="56476931257058635662018558100729360659876486117910"
'   s+="45334885034611365768675324944166803962657978771855"
'   s+="60845529654126654085306143444318586769751456614068"
'   s+="00700237877659134401712749470420562230538994561314"
'   s+="07112700040785473326993908145466464588079727082668"
'   s+="30634328587856983052358089330657574067954571637752"
'   s+="54202114955761581400250126228594130216471550979259"
'   s+="23099079654737612551765675135751782966645477917450"
'   s+="11299614890304639947132962107340437518957359614589"
'   s+="01938971311179042978285647503203198691514028708085"
'   s+="99048010941214722131794764777262241425485454033215"
'   s+="71853061422881375850430633217518297986622371721591"
'   s+="60771669254748738986654949450114654062843366393790"
'   s+="03976926567214638530673609657120918076383271664162"
'   s+="74888800786925602902284721040317211860820419000422"
'   s+="96617119637792133757511495950156604963186294726547"
'   s+="36425230817703675159067350235072835405670403867435"
'   s+="13622224771589150495309844489333096340878076932599"
'   s+="39780541934144737744184263129860809988868741326047"
'   s+="21569516239658645730216315981931951673538129741677"
'   s+="29478672422924654366800980676928238280689964004824"
'   s+="35403701416314965897940924323789690706977942236250"
'   s+="82216889573837986230015937764716512289357860158816"
'   s+="17557829735233446042815126272037343146531977774160"
'   s+="31990665541876397929334419521541341899485444734567"
'   s+="38316249934191318148092777710386387734317720754565"
'   s+="45322077709212019051660962804909263601975988281613"
'   s+="32316663652861932668633606273567630354477628035045"
'   s+="07772355471058595487027908143562401451718062464362"
'   s+="67945612753181340783303362542327839449753824372058"
'   s+="35311477119926063813346776879695970309833913077109"
'   s+="87040859133746414428227726346594704745878477872019"
'   s+="27715280731767907707157213444730605700733492436931"
'   s+="13835049316312840425121925651798069411352801314701"
'   s+="30478164378851852909285452011658393419656213491434"
'   s+="15956258658655705526904965209858033850722426482939"
'   s+="72858478316305777756068887644624824685792603953527"
'   s+="73480304802900587607582510474709164396136267604492"
'   s+="56274204208320856611906254543372131535958450687724"
'   s+="60290161876679524061634252257719542916299193064553"
'   s+="77991403734043287526288896399587947572917464263574"
'   s+="55254079091451357111369410911939325191076020825202"
'   s+="61879853188770584297259167781314969900901921169717"
'   s+="37278476847268608490033770242429165130050051683233"
'   s+="64350389517029893922334517220138128069650117844087"
'   s+="45196012122859937162313017114448464090389064495444"
'   s+="00619869075485160263275052983491874078668088183385"
'   s+="10228334508504860825039302133219715518430635455007"
'   s+="66828294930413776552793975175461395398468339363830"
'   s+="47461199665385815384205685338621867252334028308711"
'   s+="23282789212507712629463229563989898935821167456270"
'   s+="10218356462201349671518819097303811980049734072396"
'   s+="10368540664319395097901906996395524530054505806855"
'   s+="01956730229219139339185680344903982059551002263535"
'   s+="36192041994745538593810234395544959778377902374216"
'   s+="17271117236434354394782218185286240851400666044332"
'   s+="58885698670543154706965747458550332323342107301545"
'   s+="94051655379068662733379958511562578432298827372319"
'   s+="89875714159578111963583300594087306812160287649628"
'   s+="67446047746491599505497374256269010490377819868359"
'   s+="38146574126804925648798556145372347867330390468838"
'   s+="34363465537949864192705638729317487233208376011230"
'   s+="29911367938627089438799362016295154133714248928307"
'   s+="22012690147546684765357616477379467520049075715552"
'   s+="78196536213239264061601363581559074220202031872776"
'   s+="05277219005561484255518792530343513984425322341576"
'   s+="23361064250639049750086562710953591946589751413103"
'   s+="48227693062474353632569160781547818115284366795706"
'   s+="11086153315044521274739245449454236828860613408414"
'   s+="86377670096120715124914043027253860764823634143346"
'   s+="23518975766452164137679690314950191085759844239198"
'   s+="62916421939949072362346468441173940326591840443780"
'   s+="51333894525742399508296591228508555821572503107125"
'   s+="70126683024029295252201187267675622041542051618416"
'   s+="34847565169998116141010029960783869092916030288400"
'   s+="26910414079288621507842451670908700069928212066041"
'   s+="83718065355672525325675328612910424877618258297651"
'   s+="57959847035622262934860034158722980534989650226291"
'   s+="74878820273420922224533985626476691490556284250391"
'   s+="27577102840279980663658254889264880254566101729670"
'   s+="26640765590429099456815065265305371829412703369313"
'   s+="78517860904070866711496558343434769338578171138645"
'   s+="58736781230145876871266034891390956200993936103102"
'   s+="91616152881384379099042317473363948045759314931405"
'   s+="29763475748119356709110137751721008031559024853090"
'   s+="66920376719220332290943346768514221447737939375170"
'   s+="34436619910403375111735471918550464490263655128162"
'   s+="28824462575916333039107225383742182140883508657391"
'   s+="77150968288747826569959957449066175834413752239709"
'   s+="68340800535598491754173818839994469748676265516582"
'   s+="76584835884531427756879002909517028352971634456212"
'   s+="96404352311760066510124120065975585127617858382920"
'   s+="41974844236080071930457618932349229279650198751872"
'   s+="12726750798125547095890455635792122103334669749923"
'   s+="56302549478024901141952123828153091140790738602515"
'   s+="22742995818072471625916685451333123948049470791191"
'   s+="53267343028244186041426363954800044800267049624820"
'   s+="17928964766975831832713142517029692348896276684403"
'   s+="23260927524960357996469256504936818360900323809293"
'   s+="45958897069536534940603402166544375589004563288225"
'   s+="05452556405644824651518754711962184439658253375438"
'   s+="85690941130315095261793780029741207665147939425902"
'   s+="98969594699556576121865619673378623625612521632086"
'   s+="28692221032748892186543648022967807057656151446320"
'   s+="46927906821207388377814233562823608963208068222468"
'   s+="01224826117718589638140918390367367222088832151375"
'   s+="56003727983940041529700287830766709444745601345564"
'   s+="17254370906979396122571429894671543578468788614445"
'   s+="81231459357198492252847160504922124247014121478057"
'   s+="34551050080190869960330276347870810817545011930714"
'   s+="12233908663938339529425786905076431006383519834389"
'   s+="34159613185434754649556978103829309716465143840700"
'   s+="70736041123735998434522516105070270562352660127648"
'   s+="48308407611830130527932054274628654036036745328651"
'   s+="05706587488225698157936789766974220575059683440869"
'   s+="73502014102067235850200724522563265134105592401902"
'   s+="74216248439140359989535394590944070469120914093870"
'   s+="01264560016237428802109276457931065792295524988727"
'   s+="584610126483699989225695968815920560010165525637568"
'   pi_dec.dec_num=str2fp(s)
'End Scope
'#endif



Function fp2str_exp(Byref n As decfloat_struct, byval places as long=NUM_DIGITS) As String
    Dim As Integer i, ex, s
    Dim As String v,f, ts
    If n.exponent<>0 Then
        ex=(n.exponent And &h7FFFFFFF)-float_BIAS-1
    Else
        ex=0
    End If
    If n.sign Then v="-" Else v=" "
    ts=str(n.mantissa[0])
    if len(ts)<8 then
      ts=ts+string(8-len(ts),"0")
   end if
    v=v+left(ts,1)+"."+mid(ts,2)
    For i=1 To NUM_DWORDS-1
      ts=str(n.mantissa[i])
      if len(ts)<8 then
         ts=string(8-len(ts),"0")+ts
      end if      
        v=v+ts
    Next
    v=left(v,places+3)
    f=Str(Abs(ex))
    f=String(5-Len(f),"0")+f
    If ex<0 Then v=v+"E-" Else v=v+"E+"
    v=v+f
    return v
End Function

'integer part of num
function fpfix( byref num as decfloat_struct ) as decfloat_struct
   dim as decfloat_struct ip
   dim as long ex, ex2, j, k
   
   ex=(num.exponent And &h7FFFFFFF)-float_BIAS
   if ex<1 then
      return ip
   end if
   if ex>=(NUM_DIGITS) then
      return num
   end if
   ex2=ex\8
   k=ex2
   j=ex mod 8
   while ex2>0
      ex2-=1
      ip.mantissa[ex2]=num.mantissa[ex2]
   wend
   if j=1 then
      ip.mantissa[k]=10000000*(num.mantissa[k]\10000000)
   elseif j=2 then
      ip.mantissa[k]=1000000*(num.mantissa[k]\1000000)
   elseif j=3 then
      ip.mantissa[k]=100000*(num.mantissa[k]\100000)
   elseif j=4 then
      ip.mantissa[k]=10000*(num.mantissa[k]\10000)
   elseif j=5 then
      ip.mantissa[k]=1000*(num.mantissa[k]\1000)
   elseif j=6 then
      ip.mantissa[k]=100*(num.mantissa[k]\100)
   elseif j=7 then
      ip.mantissa[k]=10*(num.mantissa[k]\10)
   elseif j=8 then
      ip.mantissa[k]=num.mantissa[k]
   end if
   ip.exponent=ex+float_BIAS
   ip.sign=num.sign
   return ip
end function

Declare Function si2fp(ByVal m As LongInt, ByVal dwords As Long=NUM_DWORDS) As decfloat_struct
Declare Function fp2str_fix (ByRef n As decfloat_struct, ByVal places As Long=NUM_DIGITS) As String

function fpfix_exp( byref num as decfloat_struct, byval places as long=NUM_DIGITS ) as string
   dim as decfloat_struct ip, tmp
   dim as long ex, ex2, j, k, d
   dim as string s=""
   
   if places<(NUM_DIGITS-2) then
      places=places+1
   end if
   ex=places
   if ex<1 then
      return "0"
   end if
   if ex>=(NUM_DIGITS) then
      return fp2str_exp (num, places)
   end if
   ex2=ex\8
   k=ex2
   j=ex mod 8
   while ex2>0
      ex2-=1
      ip.mantissa[ex2]=num.mantissa[ex2]
   wend

   if j=0 then
      d=num.mantissa[k]\10000000
   elseif j=1 then
      ip.mantissa[k]=10000000*(num.mantissa[k]\10000000)
      d=(num.mantissa[k]\1000000) mod 10
   elseif j=2 then
      ip.mantissa[k]=1000000*(num.mantissa[k]\1000000)
      d=(num.mantissa[k]\100000) mod 10
   elseif j=3 then
      ip.mantissa[k]=100000*(num.mantissa[k]\100000)
      d=(num.mantissa[k]\10000) mod 10
   elseif j=4 then
      ip.mantissa[k]=10000*(num.mantissa[k]\10000)
      d=(num.mantissa[k]\1000) mod 10 
   elseif j=5 then
      ip.mantissa[k]=1000*(num.mantissa[k]\1000)
      d=(num.mantissa[k]\100) mod 10
   elseif j=6 then
      ip.mantissa[k]=100*(num.mantissa[k]\100)
      d=(num.mantissa[k]\10) mod 10
   elseif j=7 then
      ip.mantissa[k]=10*(num.mantissa[k]\10)
      d=(num.mantissa[k]) mod 10
   end if
   ip.exponent=ex+float_BIAS
   tmp=si2fp(1)
   if d>=5 then
      ip=fpadd(ip, tmp)
   end if
   If ip.exponent>ex+float_BIAS Then
      ip.exponent=num.exponent+1
   else
      ip.exponent=num.exponent
   end if
   ip.sign=num.sign
   return fp2str_exp (ip, places-1)
end function

Declare Function fp2str(ByRef n As decfloat, ByVal places As Long) As String

Function fpfix_rndu(ByRef num As decfloat_struct, ByVal places As Long = NUM_DIGITS) As String
   dim as decfloat_struct ip
   dim as long   ex, ex2, j, k, d
   dim as string s = ""
   If num.exponent <> 0 Then
      ex = (num.exponent And &H7FFFFFFF) - float_BIAS
   else
      ex = 0
   End If
   If places > NUM_DIGITS Or Abs(ex) > (NUM_DIGITS -2) Or (Abs(ex) + places) > (NUM_DIGITS -2) Then
      places = NUM_DIGITS -2
   Else
      places = places + ex
   End If
   ex = places
   if places > (NUM_DIGITS -2) then
      dim as decfloat tmp
      tmp.dec_num = num
      Return fp2str(tmp, places)
   end if
   if ex < 1 then
      return " 0"
   end if
   ex2 = ex \ 8
   k   = ex2
   j   = ex mod 8
   while ex2 > 0
      ex2 -= 1
      ip.mantissa[ex2] = num.mantissa[ex2]
   wend
   
   if j = 0 then
      d = num.mantissa[k] \ 10000000
   elseif j = 1 then
      ip.mantissa[k] = 10000000 * (num.mantissa[k] \ 10000000)
      d = (num.mantissa[k] \ 1000000) mod 10
   elseif j = 2 then
      ip.mantissa[k] = 1000000 * (num.mantissa[k] \ 1000000)
      d = (num.mantissa[k] \ 100000) mod 10
   elseif j = 3 then
      ip.mantissa[k] = 100000 * (num.mantissa[k] \ 100000)
      d = (num.mantissa[k] \ 10000) mod 10
   elseif j = 4 then
      ip.mantissa[k] = 10000 * (num.mantissa[k] \ 10000)
      d = (num.mantissa[k] \ 1000) mod 10
   elseif j = 5 then
      ip.mantissa[k] = 1000 * (num.mantissa[k] \ 1000)
      d = (num.mantissa[k] \ 100) mod 10
   elseif j = 6 then
      ip.mantissa[k] = 100 * (num.mantissa[k] \ 100)
      d = (num.mantissa[k] \ 10) mod 10
   elseif j = 7 then
      ip.mantissa[k] = 10 * (num.mantissa[k] \ 10)
      d = (num.mantissa[k]) mod 10
   end if
   
   ip.exponent = ex + float_BIAS
   If d >= 5 Then
      ip = fpadd(ip, si2fp(1))
   end if
   If ip.exponent > ex + float_BIAS Then
      ip.exponent = num.exponent + 1
      places      = places       + 1
   else
      ip.exponent = num.exponent
   end if
   ip.sign = num.sign
   Return fp2str_fix(ip, places)
end function

function fpfix_is_odd( byref num as decfloat_struct ) as long
   dim as long ex, ex2, j, k
   
   ex=(num.exponent And &h7FFFFFFF)-float_BIAS
   if ex<1 then
      return 0
   end if
   if ex>=(NUM_DIGITS) then
      'print "error in function fpfix_is_odd"
      return 99999999
   end if
   ex2=ex\8
   k=ex2
   j=ex mod 8

   if j=1 then
      return (num.mantissa[k]\10000000) and 1
   elseif j=2 then
      return (num.mantissa[k]\1000000) and 1
   elseif j=3 then
      return (num.mantissa[k]\100000) and 1
   elseif j=4 then
      return (num.mantissa[k]\10000) and 1
   elseif j=5 then
      return (num.mantissa[k]\1000) and 1
   elseif j=6 then
      return (num.mantissa[k]\100) and 1
   elseif j=7 then
      return (num.mantissa[k]\10) and 1
   elseif j=8 then
      return num.mantissa[k] and 1
   end if
   return 0
end function

Function fp2dbl(Byref n As decfloat_struct) As double
    Dim As Integer i, ex, s
    Dim As String v,f, ts
    If n.exponent>0 Then
        ex=(n.exponent And &h7FFFFFFF)-float_BIAS-1
    Else
        ex=0
    End If
    If n.sign Then v="-" Else v=" "
    ts=str(n.mantissa[0])
    if len(ts)<8 then
      ts=ts+string(8-len(ts),"0")
   end if
   v=v+left(ts,1)+"."+mid(ts,2)
   ts=str(n.mantissa[1])
   if len(ts)<8 then
      ts=string(8-len(ts),"0")+ts
   end if      
   v=v+ts

    f=Str(Abs(ex))
    f=String(5-Len(f),"0")+f
    If ex<0 Then v=v+"E-" Else v=v+"E+"
    v=v+f
    return val(v)
End Function

Function fp2str_fix(ByRef n As decfloat_struct, ByVal places As Long = NUM_DIGITS) As String
   Dim As Integer i, ex
   Dim As String  v, f, ts, s
   If n.exponent <> 0 Then
      ex = (n.exponent And &H7FFFFFFF) - float_BIAS - 1
   Else
      ex = 0
   End If
   
   if abs(ex) > (NUM_DIGITS -2) then
      Return fp2str_exp(n, places)
   End If
   If n.sign Then s = "-" Else s = " "

   ts = Trim(Str(n.mantissa[0]))
   If Len(ts) < 8 Then
      ts = ts + String(8 - Len(ts), "0")
   End If
   v = ts
   For i = 1 To NUM_DWORDS -1
      ts = Trim(Str(n.mantissa[i]))
      If Len(ts) < 8 Then
         ts = String(8 - Len(ts), "0") + ts
      End If
      v = v + ts
   Next

   If places < NUM_DIGITS Then
      v = Left(v, places)
   End If
   If ex = 0 Then
      v = Left(v, 1) + "." + Mid(v, 2)
   Elseif ex < 0 Then
      v = "0." + String(Abs(ex) - 1, "0") + v
   Elseif ex > 0 Then
      v = Left(v, ex + 1) + "." + Mid(v, ex + 2)
   End If
   i = instr(v, ".")
   if i = len(v) then
      v = left(v, i -1)
   End If
   Return s + v
End Function

Function fp2str(ByRef n As decfloat, ByVal places As Long ) As String
   If places < 0          Then places = NUM_DIGITS -2
   If places > NUM_DIGITS Then places = NUM_DIGITS -2
   Dim As Integer ex
   If n.dec_num.exponent <> 0 Then
      ex = (n.dec_num.exponent And &H7FFFFFFF) - float_BIAS -1
   Else
      ex = 0
   End If
   If Abs(ex) < places AndAlso places < (NUM_DIGITS -1) Then
      Return fpfix_rndu(n.dec_num, places)
   Else
      Return fpfix_exp(n.dec_num, places)
   end if
End Function

Function str2fp(ByVal value As String) As decfloat_struct
   Dim As Integer j, s, d, e, ep, ex, es, i, f, fp, fln
   Dim As String  c, f1, f2, f3, ts
   Dim As Ulong   ulng
   Dim n As decfloat_struct
   j     = 1
   s     = 1
   d     = 0
   e     = 0
   ep    = 0
   ex    = 0
   es    = 1
   i     = 0
   f     = 0
   fp    = 0
   f1    = ""
   f2    = ""
   f3    = ""
   value = Ucase(value)
   fln   = Len(value)
   
   While j <= fln
      c = Mid(value, j, 1)
      If ep = 1 Then
         If c = " " Then
            j = j + 1
            Continue While
         Endif
         If c = "-" Then
            es = - es
            c  = ""
         Endif
         If c = "+" Then
            j = j + 1
            Continue While
         Endif
         If (c = "0") And (f3 = "") Then
            j = j + 1
            Continue While
         EndIf
         If (c > "/") And (c < ":") Then 'c is digit between 0 and 9
            f3 = f3 + c
            ex = 10 *ex + (Asc(c) -48)
            j  = j + 1
            Continue While
         Endif
      Endif
      
      If c = " " Then
         j = j + 1
         Continue While
      EndIf
      If c = "-" Then
         s = - s
         j = j + 1
         Continue While
      Endif
      If c = "+" Then
         j = j + 1
         Continue While
      Endif
      If c = "." Then
         If d = 1 Then
            j = j + 1
            Continue While
         Endif
         d = 1
      Endif
      If (c > "/") And (c < ":") Then 'c is digit between 0 and 9
         If ((c = "0") And (i = 0)) Then
            If d = 0 Then
               j = j + 1
               Continue While
            Endif
            If (d = 1) And (f = 0) Then
               e = e -1
               j = j + 1
               Continue While
            Endif
         Endif
         If d = 0 Then
            f1 = f1 + c
            i  = i  + 1
         Else
            If (c > "0") Then
               fp = 1
            Endif
            f2 = f2 + c
            f  = f  + 1
         Endif
      EndIf
      If c = "E" or c = "D" Then
         ep = 1
      Endif
      j = j + 1
   Wend
   If fp = 0 Then
      f  = 0
      f2 = ""
   Endif
   
   If s = -1 Then s = &H8000 Else s = 0
   n.sign = s
   ex = es *ex -1 + i + e
   f1     = f1 + f2
   f1     = Mid(f1, 1, 1) + Right(f1, Len(f1) -1)
   fln    = Len(f1)
   If Len(f1) > (NUM_DIGITS + 1 + 8) Then
      f1 = Mid(f1, 1, (NUM_DIGITS + 1 + 8))
   Endif
   While Len(f1) < (NUM_DIGITS + 1 + 8)
      f1 = f1 + "0"
   Wend
   j = 1
   For i = 0 To NUM_DWORDS
      ts            = Mid(f1, j, 8)
      ulng          = ValUInt(ts)
      n.mantissa[i] = ulng
      If ulng <> 0 Then fp = 1
      j += 8
   Next
   If fp Then n.exponent = (ex + float_BIAS + 1) Else n.exponent = 0
   Return n
End Function

Function si2fp(ByVal m As LongInt, ByVal dwords As Long=NUM_DWORDS) As decfloat_struct
   if dwords>NUM_DWORDS then dwords=NUM_DWORDS
   dim as decfloat_struct fac1
   dim as long i, n0, n1
   dim as longint n=abs(m)
   
   if n>9999999999999999ull then
      fac1=str2fp(str(m))
      return fac1
   end if
   
   For i=1 To dwords
      fac1.mantissa[i]=0
   Next
   
   if m=0 then
      fac1.exponent=0
      fac1.sign=0
      return fac1
   end if

   fac1.exponent=float_BIAS
   if n<100000000  then
      if n<10 then
         fac1.mantissa[0]=n*10000000
         fac1.exponent+=1
      elseif n<100 then
         fac1.mantissa[0]=n*1000000
         fac1.exponent+=2
      elseif n<1000 then
         fac1.mantissa[0]=n*100000
         fac1.exponent+=3
      elseif n<10000 then
         fac1.mantissa[0]=n*10000
         fac1.exponent+=4
      elseif n<100000 then
         fac1.mantissa[0]=n*1000
         fac1.exponent+=5
      elseif n<1000000 then
         fac1.mantissa[0]=n*100
         fac1.exponent+=6
      elseif n<10000000 then
         fac1.mantissa[0]=n*10
         fac1.exponent+=7
      elseif n<100000000 then
         fac1.mantissa[0]=n
         fac1.exponent+=8
      end if
   end if
   if n>99999999 then
      fac1.exponent+=8
      if n<1000000000 then
         fac1.mantissa[0]=n\10
         fac1.mantissa[1]=(n mod 10)*10000000
         fac1.exponent+=1
      elseif n<100000000000 then
         fac1.mantissa[0]=n\100
         fac1.mantissa[1]=(n mod 100)*1000000
         fac1.exponent+=2
      elseif n<1000000000000 then
         fac1.mantissa[0]=n\1000
         fac1.mantissa[1]=(n mod 1000)*100000
         fac1.exponent+=3
      elseif n<10000000000000 then
         fac1.mantissa[0]=n\10000
         fac1.mantissa[1]=(n mod 10000)*10000
         fac1.exponent+=4
      elseif n<100000000000000 then
         fac1.mantissa[0]=n\100000
         fac1.mantissa[1]=(n mod 100000)*1000
         fac1.exponent+=5
      elseif n<1000000000000000 then
         fac1.mantissa[0]=n\1000000
         fac1.mantissa[1]=(n mod 1000000)*100
         fac1.exponent+=6
      elseif n<10000000000000000 then
         fac1.mantissa[0]=n\10000000
         fac1.mantissa[1]=(n mod 10000000)*10
         fac1.exponent+=7
      elseif n<100000000000000000 then
         fac1.mantissa[0]=n\100000000
         fac1.mantissa[1]=n mod 100000000
         fac1.exponent+=8
      end if
   end if
   if m<0 then
      fac1.sign=&H8000
   else
      fac1.sign=0
   end if
   return fac1
end function

Sub RSHIFT_1(Byref mantissa As decfloat_struct, byval dwords as long=NUM_DWORDS)
   if dwords>NUM_DWORDS then dwords=NUM_DWORDS

   dim as ulong v1, v2
   For i As Long=dwords To 1 Step -1
      v1=mantissa.mantissa[i]\10
      v2=mantissa.mantissa[i-1] mod 10
      v2=v2*10000000+v1
      mantissa.mantissa[i]=v2
   Next
   mantissa.mantissa[0]=mantissa.mantissa[0]\10
End Sub

Sub LSHIFT_1(Byref mantissa As decfloat_struct, byval dwords as long=NUM_DWORDS)
   if dwords>NUM_DWORDS then dwords=NUM_DWORDS

   dim as ulong v1, v2
   For i As Long=0 To dwords-1
      v1=mantissa.mantissa[i] mod 10000000
      v2=mantissa.mantissa[i+1]\10000000
      mantissa.mantissa[i]=v1*10+v2
      mantissa.mantissa[i+1]=mantissa.mantissa[i+1] mod 10000000
   Next
   mantissa.mantissa[dwords]=10*(mantissa.mantissa[dwords] mod 10000000)
End Sub

Sub RSHIFT_2(Byref mantissa As decfloat_struct, byval dwords as long=NUM_DWORDS)
   if dwords>NUM_DWORDS then dwords=NUM_DWORDS

   dim as ulong v1, v2
   For i As Long=dwords To 1 Step -1
      v1=mantissa.mantissa[i]\100
      v2=mantissa.mantissa[i-1] mod 100
      v2=v2*1000000+v1
      mantissa.mantissa[i]=v2
   Next
   mantissa.mantissa[0]=mantissa.mantissa[0]\100
End Sub

Sub LSHIFT_2(Byref mantissa As decfloat_struct, byval dwords as long=NUM_DWORDS)
   if dwords>NUM_DWORDS then dwords=NUM_DWORDS

   dim as ulong v1, v2
   For i As Long=0 To dwords-1
      v1=mantissa.mantissa[i] mod 1000000
      v2=mantissa.mantissa[i+1]\1000000
      mantissa.mantissa[i]=v1*100+v2
      mantissa.mantissa[i+1]=mantissa.mantissa[i+1] mod 1000000
   Next
   mantissa.mantissa[dwords]=100*(mantissa.mantissa[dwords] mod 1000000)
End Sub

Sub RSHIFT_3(Byref mantissa As decfloat_struct, byval dwords as long=NUM_DWORDS)
   if dwords>NUM_DWORDS then dwords=NUM_DWORDS

   dim as ulong v1, v2
   For i As Long=dwords To 1 Step -1
      v1=mantissa.mantissa[i]\1000
      v2=mantissa.mantissa[i-1] mod 1000
      v2=v2*100000+v1
      mantissa.mantissa[i]=v2
   Next
   mantissa.mantissa[0]=mantissa.mantissa[0]\1000
End Sub

Sub LSHIFT_3(Byref mantissa As decfloat_struct, byval dwords as long=NUM_DWORDS)
   if dwords>NUM_DWORDS then dwords=NUM_DWORDS

   dim as ulong v1, v2
   For i As Long=0 To dwords-1
      v1=mantissa.mantissa[i] mod 100000
      v2=mantissa.mantissa[i+1]\100000
      mantissa.mantissa[i]=v1*1000+v2
      mantissa.mantissa[i+1]=mantissa.mantissa[i+1] mod 100000
   Next
   mantissa.mantissa[dwords]=1000*(mantissa.mantissa[dwords] mod 100000)
End Sub

Sub RSHIFT_4(Byref mantissa As decfloat_struct, byval dwords as long=NUM_DWORDS)
   if dwords>NUM_DWORDS then dwords=NUM_DWORDS

   dim as ulong v1, v2
   For i As Long=dwords To 1 Step -1
      v1=mantissa.mantissa[i]\10000
      v2=mantissa.mantissa[i-1] mod 10000
      v2=v2*10000+v1
      mantissa.mantissa[i]=v2
   Next
   mantissa.mantissa[0]=mantissa.mantissa[0]\10000
End Sub

Sub LSHIFT_4(Byref mantissa As decfloat_struct, byval dwords as long=NUM_DWORDS)
   if dwords>NUM_DWORDS then dwords=NUM_DWORDS

   dim as ulong v1, v2
   For i As Long=0 To dwords-1
      v1=mantissa.mantissa[i] mod 10000
      v2=mantissa.mantissa[i+1]\10000
      mantissa.mantissa[i]=v1*10000+v2
      mantissa.mantissa[i+1]=mantissa.mantissa[i+1] mod 10000
   Next
   mantissa.mantissa[dwords]=10000*(mantissa.mantissa[dwords] mod 10000)
End Sub

Sub RSHIFT_5(Byref mantissa As decfloat_struct, byval dwords as long=NUM_DWORDS)
   if dwords>NUM_DWORDS then dwords=NUM_DWORDS

   dim as ulong v1, v2
   For i As Long=dwords To 1 Step -1
      v1=mantissa.mantissa[i]\100000
      v2=mantissa.mantissa[i-1] mod 100000
      v2=v2*1000+v1
      mantissa.mantissa[i]=v2
   Next
   mantissa.mantissa[0]=mantissa.mantissa[0]\100000
End Sub

Sub LSHIFT_5(Byref mantissa As decfloat_struct, byval dwords as long=NUM_DWORDS)
   if dwords>NUM_DWORDS then dwords=NUM_DWORDS

   dim as ulong v1, v2
   For i As Long=0 To dwords-1
      v1=mantissa.mantissa[i] mod 1000
      v2=mantissa.mantissa[i+1]\1000
      mantissa.mantissa[i]=v1*100000+v2
      mantissa.mantissa[i+1]=mantissa.mantissa[i+1] mod 1000
   Next
   mantissa.mantissa[dwords]=100000*(mantissa.mantissa[dwords] mod 1000)
End Sub

Sub RSHIFT_6(Byref mantissa As decfloat_struct, byval dwords as long=NUM_DWORDS)
   if dwords>NUM_DWORDS then dwords=NUM_DWORDS

   dim as ulong v1, v2
   For i As Long=dwords To 1 Step -1
      v1=mantissa.mantissa[i]\1000000
      v2=mantissa.mantissa[i-1] mod 1000000
      v2=v2*100+v1
      mantissa.mantissa[i]=v2
   Next
   mantissa.mantissa[0]=mantissa.mantissa[0]\1000000
End Sub

Sub LSHIFT_6(Byref mantissa As decfloat_struct, byval dwords as long=NUM_DWORDS)
   if dwords>NUM_DWORDS then dwords=NUM_DWORDS

   dim as ulong v1, v2
   For i As Long=0 To dwords-1
      v1=mantissa.mantissa[i] mod 100
      v2=mantissa.mantissa[i+1]\100
      mantissa.mantissa[i]=v1*1000000+v2
      mantissa.mantissa[i+1]=mantissa.mantissa[i+1] mod 100
   Next
   mantissa.mantissa[dwords]=1000000*(mantissa.mantissa[dwords] mod 100)
End Sub

Sub RSHIFT_7(Byref mantissa As decfloat_struct, byval dwords as long=NUM_DWORDS)
   if dwords>NUM_DWORDS then dwords=NUM_DWORDS

   dim as ulong v1, v2
   For i As Long=dwords To 1 Step -1
      v1=mantissa.mantissa[i]\10000000
      v2=mantissa.mantissa[i-1] mod 10000000
      v2=v2*10+v1
      mantissa.mantissa[i]=v2
   Next
   mantissa.mantissa[0]=mantissa.mantissa[0]\10000000
End Sub

Sub LSHIFT_7(Byref mantissa As decfloat_struct, byval dwords as long=NUM_DWORDS)
   if dwords>NUM_DWORDS then dwords=NUM_DWORDS

   dim as ulong v1, v2
   For i As Long=0 To dwords-1
      v1=mantissa.mantissa[i] mod 10
      v2=mantissa.mantissa[i+1]\10
      mantissa.mantissa[i]=v1*10000000+v2
      mantissa.mantissa[i+1]=mantissa.mantissa[i+1] mod 10
   Next
   mantissa.mantissa[dwords]=10000000*(mantissa.mantissa[dwords] mod 10)
End Sub

Sub RSHIFT_8(Byref mantissa As decfloat_struct, byval dwords as long=NUM_DWORDS)
   if dwords>NUM_DWORDS then dwords=NUM_DWORDS

   For i As Long=dwords To 1 Step -1
      mantissa.mantissa[i]=mantissa.mantissa[i-1]
   Next
   mantissa.mantissa[0]=0
End Sub

Sub LSHIFT_8(Byref mantissa As decfloat_struct, byval dwords as long=NUM_DWORDS)
   if dwords>NUM_DWORDS then dwords=NUM_DWORDS

   For i As Long=0 To dwords-1
      mantissa.mantissa[i]=mantissa.mantissa[i+1]
   Next
   mantissa.mantissa[dwords]=0
End Sub

Function fpcmp(Byref x As DecFloat_struct, Byref y As DecFloat_struct, Byval dwords As Long=NUM_DWORDS) As Long
   If dwords>NUM_DWORDS Then dwords=NUM_DWORDS
      Dim As Long i
      Dim As Longint c
      If x.sign < y.sign Then
         return -1
      end if
      If x.sign > y.sign Then
         return 1
      end if
      If x.exponent<y.exponent Then
         if x.sign=0 then
            Return -1
         else
            return 1
         end if
      end if
      If x.exponent>y.exponent Then
         if x.sign=0 then
            Return 1
         else
            return -1
         end if
      end if

      For i=0 To dwords
         c=clngint(x.mantissa[i])-clngint(y.mantissa[i])
         If c<>0 Then Exit For
      Next
      if c=0 then return 0
      If c<0 Then
         if x.sign=0 then
            Return -1
         else
            return 1
         end if
      end if
      If c>0 Then
         if x.sign=0 then
            Return 1
         else
            return -1
         end if
      end if
End Function

Function NORM_FAC1(Byref fac1 As decfloat_struct, byval dwords as long=NUM_DWORDS) As Integer
   if dwords>NUM_DWORDS then dwords=NUM_DWORDS
    ' normalize the number in fac1
    ' all routines exit through this one.

    'see if the mantissa is all zeros.
    'if so, set the exponent and sign equal to 0.
    Dim As Integer i,er=0,f=0
    For i=0 To dwords
        If fac1.mantissa[i]>0 Then f=1 
    Next
    If f=0 Then
        fac1.exponent=0
        fac1.sign=0
        Exit Function
      'if the highmost Digit in fac1_man is nonzero,
      'shift the mantissa right 1 Digit and
      'increment the exponent
    Elseif fac1.mantissa[0]>99999999 Then
        RSHIFT_1(fac1, dwords)
        fac1.exponent+=1
    Else
      'now shift fac1_man 1 to the left until a
      'nonzero digit appears in the next-to-highest
      'Digit of fac1_man.  decrement exponent for
      'each shift.
        While fac1.mantissa[0]=0
            LSHIFT_8(fac1, dwords)
            fac1.exponent-=8
            If fac1.exponent=0 Then
                NORM_FAC1=EXPU_ERR
                Exit Function
            End If
        Wend
      if fac1.mantissa[0]<10 then
         LSHIFT_7(fac1, dwords)
         fac1.exponent-=7
      elseif fac1.mantissa[0]<100 then
         LSHIFT_6(fac1, dwords)
         fac1.exponent-=6
      elseif fac1.mantissa[0]<1000 then
         LSHIFT_5(fac1, dwords)
         fac1.exponent-=5
      elseif fac1.mantissa[0]<10000 then
         LSHIFT_4(fac1, dwords)
         fac1.exponent-=4
      elseif fac1.mantissa[0]<100000 then
         LSHIFT_3(fac1, dwords)
         fac1.exponent-=3
      elseif fac1.mantissa[0]<1000000 then
         LSHIFT_2(fac1, dwords)
         fac1.exponent-=2
      elseif fac1.mantissa[0]<10000000 then
         LSHIFT_1(fac1, dwords)
         fac1.exponent-=1
      end if
    End If
    'check for overflow/underflow
    If fac1.exponent<0 Then
        NORM_FAC1=EXPO_ERR
    End If
End Function

Sub fpadd_aux(Byref fac1 As decfloat_struct, Byref fac2 As decfloat_struct, byval dwords as long=NUM_DWORDS)
   if dwords>NUM_DWORDS then dwords=NUM_DWORDS
   dim as long v, c, i
   c=0
   for i=dwords to 1 step -1
      v=fac2.mantissa[i]+fac1.mantissa[i]+c
      if v>99999999 then
         v=v-100000000
         c=1
      else
         c=0
      end if
      fac1.mantissa[i]=v
   next
   v=fac1.mantissa[0]+fac2.mantissa[0]+c
   fac1.mantissa[0]=v

    NORM_FAC1(fac1, dwords)

End Sub

Sub fpsub_aux(Byref fac1 As decfloat_struct, Byref fac2 As decfloat_struct, byval dwords as long=NUM_DWORDS)
   if dwords>NUM_DWORDS then dwords=NUM_DWORDS
   dim as long v, c, i
   c=0
   for i=dwords to 1 step -1
      v=fac1.mantissa[i]-fac2.mantissa[i]-c
      if v<0 then
         v=v+100000000
         c=1
      else
         c=0
      end if
      fac1.mantissa[i]=v
   next
   v=fac1.mantissa[0]-fac2.mantissa[0]-c
   fac1.mantissa[0]=v

    NORM_FAC1(fac1, dwords)
End Sub

Function fpadd(Byref x As decfloat_struct, Byref y As decfloat_struct, byval dwords as long=NUM_DWORDS) As decfloat_struct
   if dwords>NUM_DWORDS then dwords=NUM_DWORDS
    
    Dim As decfloat_struct fac1,fac2
    Dim As long i, t, c, xsign, ysign
    
    xsign=x.sign:x.sign=0
    ysign=y.sign:y.sign=0
    c=fpcmp(x, y, dwords)

    x.sign=xsign
    y.sign=ysign
    If c<0 Then
        fac1=y
        fac2=x
    else
        fac1=x
        fac2=y
    end if
    t=fac1.exponent-fac2.exponent

   t=((fac1.exponent And &h7FFFFFFF)-float_BIAS-1)-((fac2.exponent And &h7FFFFFFF)-float_BIAS-1)

    if t<(NUM_DIGITS+8) then
        'The difference between the two
        'exponents indicate how many times
        'we have to multiply the mantissa
        'of FAC2 by 10 (i.e., shift it right 1 place).
        'If we have to shift more times than
        'we have dwords, the result is already in FAC1.
        t=fac1.exponent-fac2.exponent
        If t>0 And t<(NUM_DIGITS+8) Then 'shift
        
         i=t\8
         while i>0
            RSHIFT_8(fac2, dwords)
            t-=8
            i-=1
         wend
         if t=7 then
            RSHIFT_7(fac2, dwords)
         elseif t=6 then
            RSHIFT_6(fac2, dwords)
         elseif t=5 then
            RSHIFT_5(fac2, dwords)
         elseif t=4 then
            RSHIFT_4(fac2, dwords)
         elseif t=3 then
            RSHIFT_3(fac2, dwords)
         elseif t=2 then
            RSHIFT_2(fac2, dwords)
         elseif t=1 then
            RSHIFT_1(fac2, dwords)
         end if
        End If
        'See if the signs of the two numbers
        'are the same.  If so, add; if not, subtract.
        If fac1.sign=fac2.sign Then 'add
            fpadd_aux(fac1,fac2, dwords)
        Else
            fpsub_aux(fac1,fac2, dwords)
        End If
    endif
    return fac1
End Function

Function fpsub(Byref x As decfloat_struct, Byref y As decfloat_struct, byval dwords as long=NUM_DWORDS) As decfloat_struct
   if dwords>NUM_DWORDS then dwords=NUM_DWORDS
    Dim As decfloat_struct fac1,fac2
    dim as long s
    fac1=x
    fac2=y
    fac2.sign=fac2.sign xor &h8000
    fac1=fpadd(fac1,fac2, dwords)
    return fac1
End Function

Function fpmul1(Byref x As decfloat_struct, Byref y As decfloat_struct, byval dwords as long=NUM_DWORDS) As decfloat_struct
   if dwords>NUM_DWORDS then dwords=NUM_DWORDS
    Dim As decfloat_struct fac1,fac2
    Dim As Integer i, j, ex, er, den, num
    dim as longint digit, carry
    dim As ulongint  fac3(0 To dwords*2)
    
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
        return fac1
    Else
        
        If ex<0 Then
            er=EXPO_ERR
            return fac1 'Exit Function
        End If

        'clear fac3 mantissa
        For i=0 To dwords
            fac3(i)=0
        Next

      den=dwords
      while fac2.mantissa[den]=0
         den-=1
      wend
      num=dwords
      while fac1.mantissa[num]=0
         num-=1
      wend
      
      if num<den then
         swap fac1, fac2
         'fac1=y
         'fac2=x         
         swap den, num
      end if
      
      for j=den to 0 step -1
         carry=0
         digit=fac2.mantissa[j]
         for i=num to 0 step -1
            fac3(i)=fac3(i)+digit*fac1.mantissa[i]
         next
         for i=num to 0 step -1
            fac3(i)=fac3(i)+carry
            carry=fac3(i)\100000000
            fac3(i)=(fac3(i) mod 100000000)
         next
         
         for i=dwords to 1 step -1
            fac3(i)=fac3(i-1)
         next
         fac3(0)=carry
      next

      for i=0 to dwords
         fac1.mantissa[i]=fac3(i)
      next
   end if
   'now determine exponent of result.
   'as you do...watch for overflow.
   ex=fac2.exponent-float_BIAS+fac1.exponent
   fac1.exponent=ex
   'determine the sign of the product
   fac1.sign=fac1.sign Xor fac2.sign
    NORM_FAC1(fac1, dwords)
    return fac1
End Function

Function fpmul(Byref x As decfloat_struct, Byref y As decfloat_struct, byval dwords as long=NUM_DWORDS) As decfloat_struct
   if dwords>NUM_DWORDS then dwords=NUM_DWORDS
    Dim As decfloat_struct fac1,fac2
    Dim As Integer i, j, ex, er, den, num
    dim as longint digit, carry, prod
    dim As ulong  fac3(0 To dwords*2+1)
    
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
        return fac1
    Else
        
        If ex<0 Then
            er=EXPO_ERR
            return fac1 'Exit Function
        End If

        'clear fac3 mantissa
        For i=0 To dwords*2+1
            fac3(i)=0
        Next

      den=dwords
      while fac2.mantissa[den]=0
         den-=1
      wend
      num=dwords
      while fac1.mantissa[num]=0
         num-=1
      wend
      
      if num<den then
         swap fac1, fac2
         'fac1=y
         'fac2=x         
         swap den, num
      end if
      
      for j=den to 0 step -1
         carry=0
         digit=fac2.mantissa[j]
         for i=num to 0 step -1
            prod=fac3(i+j+1)+digit*fac1.mantissa[i]+carry
            carry=prod\100000000
            fac3(i+j+1)=(prod mod 100000000)
         next

         fac3(j)=carry
      next

      for i=0 to dwords
         fac1.mantissa[i]=fac3(i)
      next
   end if
   'now determine exponent of result.
   'as you do...watch for overflow.
   ex=fac2.exponent-float_BIAS+fac1.exponent
   fac1.exponent=ex
   'determine the sign of the product
   fac1.sign=fac1.sign Xor fac2.sign

    NORM_FAC1(fac1, dwords)
    return fac1
End Function

Function fpmul_si(Byref x As decfloat_struct, Byval y As longint, byval dwords as long=NUM_DWORDS) As decfloat_struct
   if dwords>NUM_DWORDS then dwords=NUM_DWORDS
    Dim As decfloat_struct fac1,fac2
    Dim As Integer count, ex, er, i, j
    Dim As long n, v, c
    dim as longint carry, digit, prod, value
    fac1=x
    digit=abs(y)
    if digit>99999999 then
      fac2=si2fp(y, dwords)
      fac1=fpmul(fac1, fac2, dwords)
      return fac1
   end if
    'check exponents.  if either is zero,
    'the result is zero
    If fac1.exponent=0 Or y=0 Then 'result is zero...clear fac1.
        fac1.sign=0
        fac1.exponent=0
        For count=0 To dwords
            fac1.mantissa[count]=0
        Next
        NORM_FAC1(fac1, dwords)
        return fac1
    Else
      if digit=1 then
         if y<0 then
            fac1.sign=fac1.sign Xor &h8000
         end if
         return fac1
      end if
        'now determine exponent of result.
        'as you do...watch for overflow.

        If ex<0 Then
            er=EXPO_ERR
            return fac1 'Exit Function
        End If
        
      carry=0
         
      for i=dwords to 0 step -1
         prod=digit*fac1.mantissa[i] +carry
         value=(prod mod 100000000)'+carry
         fac1.mantissa[i]=value
         carry=prod\100000000
      next

      if carry<10 then
         RSHIFT_1(fac1, dwords)
         fac1.exponent+=1
         fac1.mantissa[0]+=carry*10000000
      elseif carry<100 then
         RSHIFT_2(fac1, dwords)
         fac1.exponent+=2
         fac1.mantissa[0]+=carry*1000000
      elseif carry<1000 then
         RSHIFT_3(fac1, dwords)
         fac1.exponent+=3
         fac1.mantissa[0]+=carry*100000
      elseif carry<10000 then
         RSHIFT_4(fac1, dwords)
         fac1.exponent+=4
         fac1.mantissa[0]+=carry*10000
      elseif carry<100000 then
         RSHIFT_5(fac1, dwords)
         fac1.exponent+=5
         fac1.mantissa[0]+=carry*1000
      elseif carry<1000000 then
         RSHIFT_6(fac1, dwords)
         fac1.exponent+=6
         fac1.mantissa[0]+=carry*100
      elseif carry<10000000 then
         RSHIFT_7(fac1, dwords)
         fac1.exponent+=7
         fac1.mantissa[0]+=carry*10
      elseif carry<100000000 then
         RSHIFT_8(fac1, dwords)
         fac1.exponent+=8
         fac1.mantissa[0]+=carry
      end if

    End If

    NORM_FAC1(fac1, dwords)

    if y<0 then
      fac1.sign=fac1.sign Xor &h8000
   end if
    return fac1
End Function

Function fpmul_ll(Byref x As decfloat_struct, Byval y As longint, byval dwords as long=NUM_DWORDS) As decfloat_struct
   if dwords>NUM_DWORDS then dwords=NUM_DWORDS
    Dim As decfloat_struct fac1,fac2
    Dim As Integer count, ex, er, i, j
    Dim As long n, v, c
    dim as longint carry, digit, prod, value, n0, n1
    fac1=x
    digit=abs(y)
    if digit>99999999 and digit<10000000000000000ull then
      n0=digit\100000000
      n1=digit mod 100000000
      fac2=fpmul_si(fac1, n1, dwords)
      fac1.exponent+=8
      fac1=fpmul_si(fac1, n0, dwords)
      fac1=fpadd(fac1, fac2, dwords)
      if y<0 then fac1.sign=fac1.sign xor &h8000
      return fac1
   end if
   if digit>9999999999999999ull then
      fac2=str2fp(str(y))
      fac1=fpmul(fac1, fac2, dwords)
      return fac1
   end if
   fac2=si2fp(y, dwords)

    'check exponents.  if either is zero,
    'the result is zero
    If fac1.exponent=0 Or y=0 Then 'result is zero...clear fac1.
        fac1.sign=0
        fac1.exponent=0
        For count=0 To dwords
            fac1.mantissa[count]=0
        Next
        NORM_FAC1(fac1, dwords)
        return fac1
    Else
      if digit=1 then
         if y<0 then
            fac1.sign=fac1.sign Xor &h8000
         end if
         return fac1
      end if
        'now determine exponent of result.
        'as you do...watch for overflow.

        If ex<0 Then
            er=EXPO_ERR
            return fac1 'Exit Function
        End If
        
      carry=0
         
      for i=dwords to 0 step -1
         prod=digit*fac1.mantissa[i] +carry
         value=(prod mod 100000000)
         fac1.mantissa[i]=value
         carry=prod\100000000
      next

      if carry<10 then
         RSHIFT_1(fac1, dwords)
         fac1.exponent+=1
         fac1.mantissa[0]+=carry*10000000
      elseif carry<100 then
         RSHIFT_2(fac1, dwords)
         fac1.exponent+=2
         fac1.mantissa[0]+=carry*1000000
      elseif carry<1000 then
         RSHIFT_3(fac1, dwords)
         fac1.exponent+=3
         fac1.mantissa[0]+=carry*100000
      elseif carry<10000 then
         RSHIFT_4(fac1, dwords)
         fac1.exponent+=4
         fac1.mantissa[0]+=carry*10000
      elseif carry<100000 then
         RSHIFT_5(fac1, dwords)
         fac1.exponent+=5
         fac1.mantissa[0]+=carry*1000
      elseif carry<1000000 then
         RSHIFT_6(fac1, dwords)
         fac1.exponent+=6
         fac1.mantissa[0]+=carry*100
      elseif carry<10000000 then
         RSHIFT_7(fac1, dwords)
         fac1.exponent+=7
         fac1.mantissa[0]+=carry*10
      elseif carry<100000000 then
         RSHIFT_8(fac1, dwords)
         fac1.exponent+=8
         fac1.mantissa[0]+=carry
      end if

    End If

    NORM_FAC1(fac1, dwords)

    if y<0 then
      fac1.sign=fac1.sign Xor &h8000
   end if
    return fac1
End Function

Function fpinv(byref m as decfloat_struct, byval dwords as long=NUM_DWORDS) as decfloat_struct
   if dwords>NUM_DWORDS then dwords=NUM_DWORDS
    Dim As Double x
    Dim As Integer k, l, i, ex, s
   dim as long prec
    Dim As decfloat_struct r, r2, one, n
    n=m
    l=log((NUM_DIGITS+8)*0.0625)*1.5
    Dim As String v,f, ts
    If n.exponent>0 Then
        ex=(n.exponent And &h7FFFFFFF)-float_BIAS-1
    Else
        ex=0
    End If

    If n.sign Then v="-" Else v=" "
    ts=str(n.mantissa[0])
    if len(ts)<8 then
      ts=ts+string(8-len(ts),"0")
   end if
   v=v+left(ts,1)+"."+mid(ts,2)
   ts=str(n.mantissa[1])
   if len(ts)<8 then
      ts=string(8-len(ts),"0")+ts
   end if      
   v=v+ts
    x=val(v)
    If x = 0 Then Return r 'Exit Function  print "Div 0": 
    If x = 1 andalso ex=0 Then
      r=str2fp("1") 
      return r
   elseif x=1 then
      x=10
      ex-=1
   end if
   ex=(-1)-ex
   x=1/x
   r=str2fp(Str(x)) 
   r.exponent=ex+float_BIAS+1
   one.mantissa[0]=10000000
   one.exponent=float_BIAS+1
   r2=r
   prec=3
   for k=1 to l
      prec=2*prec-1
      r2=fpmul(n,r, prec)
        r2=fpsub(one, r2, prec)
        r2=fpmul(r, r2, prec)
      r=fpadd(r,r2, prec)
   next
    return r
End Function

Function fpdiv(Byref x As decfloat_struct, Byref y As decfloat_struct, byval dwords as long=NUM_DWORDS) As decfloat_struct
   if dwords>NUM_DWORDS then dwords=NUM_DWORDS
    Dim As decfloat_struct fac1, fac2
    Dim As Integer i, er, is_power_of_ten
   
   fac1=x
   fac2=y

    If fac2.exponent=0 Then ' if fac2 = 0, return
        ' a divide-by-zero error and
        ' bail out.
        for i=0 to dwords
         fac1.mantissa[i]=99999999
      next
      fac1.exponent=99999+float_BIAS+1
        er=DIVZ_ERR
        return fac1
    Elseif fac1.exponent=0 Then 'fact1=0, just return
        er=0
        return fac1
    Else
      'check to see if fac2 is a power of ten
      is_power_of_ten=0
      if fac2.mantissa[0]=10000000 then
         is_power_of_ten=1
         for i=1 to dwords
            if fac2.mantissa[i]<>0 then
               is_power_of_ten=0
               exit for
            end if
         next
      end if
      'if fac2 is a power of ten then all we need to do is to adjust the sign and exponent and we are finished
      if is_power_of_ten=1 then
         fac1.sign=fac1.sign Xor fac2.sign
         fac1.exponent=fac1.exponent-fac2.exponent+float_BIAS+1
         return fac1
      End If
      #ifndef min
         #define min(a,b) IIf(((a)<(b)),(a),(b))
      #endif


      #Macro realw(w, j)
         ((w(j - 1)*b + w(j))*b + w(j + 1))*b +Iif(Ubound(w)>=j+2,w(j+2),0)
      #Endmacro

      #Macro subtract(w, q, d, ka, kb)
         For j=ka To kb
            w(j) = w(j) - q*d(j - ka + 2)
         Next
      #Endmacro

      #Macro normalize(w, ka, q)
         w(ka) = w(ka) + w(ka - 1)*b
         w(ka - 1) = q
      #Endmacro

      #Macro finalnorm(w, kb)
         For j=kb To 3 Step -1
            carry=Iif(w(j)<0, ((-w(j) - 1)\b) + 1, Iif(w(j) >= b, -(w(j)\b), 0))
            w(j) = w(j) + carry*b
            w(j - 1) = w(j - 1) - carry
         Next
      #Endmacro

      dim as double result(1 to 2*dwords+3), n(1 to 2*dwords+3), d(1 to 2*dwords+3)
      const b=10000   
      dim as long j, last, laststep, q, t
      dim as long stp, carry
      dim as double xd, xn, rund
      dim as double w(1 to ubound(n)+4)

      for j=0 to dwords
         n(2*j+2)=fac1.mantissa[j]\10000
         n(2*j+3)=fac1.mantissa[j] mod 10000
         d(2*j+2)=fac2.mantissa[j]\10000
         d(2*j+3)=fac2.mantissa[j] mod 10000
      next
      n(1)=(fac1.exponent And &h7FFFFFFF)-float_BIAS-1
      d(1)=(fac2.exponent And &h7FFFFFFF)-float_BIAS-1
      for j=ubound(n) to ubound(w)
         w(j)=0
      next
      t=ubound(n)-1
      w(1)=n(1)-d(1)+1
      w(2)=0
      for j=2 to ubound(n)
         w(j+1)=n(j)
      next   
      xd = (d(2)*b + d(3))*b + d(4) + d(5)/b
      laststep = t + 2
      for stp=1 to laststep
         xn=RealW(w, (stp + 2))
         q=int(xn/xd)
         last = Min(stp + t + 1, ubound(W))
         subtract(w, q, d, (stp + 2), last)
         normalize(w, (stp + 2), q)
      next
      FinalNorm(w, (laststep + 1))
      laststep = iif(w(2) = 0, laststep, laststep - 1)
      rund = w(laststep + 1)/b
      w(laststep) = w(laststep) + iif(rund >= 0.5, 1, 0)
      if w(2)=0 then
         for j=1 to t+1
            result(j)=w(j+1)
         next
      else
         for j=1 to t+1
            result(j)=w(j)
         next
      end if
      result(1) = iif(w(2) = 0, w(1) - 1, w(1))
      
      for j=0 to dwords
         fac1.mantissa[j]=result(2*j+2)*10000+result(2*j+3)
      next
      NORM_FAC1(fac1, dwords)
      fac1.exponent=(result(1)+float_BIAS)
   end if
   fac1.sign=fac1.sign Xor fac2.sign
    return fac1
End Function

' sqrt(num)
Function fpsqr (byref num as decfloat_struct, byval dwords as long=NUM_DWORDS) as decfloat_struct
   if dwords>NUM_DWORDS then dwords=NUM_DWORDS
    Dim As decfloat_struct r, r2, tmp, n, half
    Dim As long ex, k, l, prec
    dim as string ts, v
    dim as double x
    l=log((NUM_DIGITS+8)*0.0625)*1.5
    'l=estimated number of iterations needed
    'first estimate is accurate to about 16 digits
    'l is approximatly = to log2((NUM_DIGITS+9)/16)
    'NUM_DIGITS+9 because decfloat has an extra 9 guard digits
    n=num
    if fpcmp(n, si2fp(0, dwords), dwords)=0 then
      r=si2fp(0, dwords)
      return r
   end if
    if fpcmp(n, si2fp(1, dwords), dwords)=0 then
      r=si2fp(1, dwords)
      return r
   end if
    if fpcmp(n, si2fp(0, dwords), dwords)<0 then
      r=si2fp(0, dwords)
      return r
   end if
'=====================================================================
   'hack to bypass the limitation of double exponent range
   'in case the number is larger than what a double can handle
   'for example, if the number is 2e500
   'we separate the exponent and mantissa in this case 2
   'if the exponent is odd then multiply the mantissa by 10
   'take the square root and assign it to decfloat
   'divide the exponent in half for square root
   'in this case 1.414213562373095e250
    If n.exponent>0 Then
        ex=(n.exponent And &h7FFFFFFF)-float_BIAS-1
    Else
        ex=0
    End If
    ts=str(n.mantissa[0])
    if len(ts)<8 then
      ts=ts+string(8-len(ts),"0")
   end if
   v=v+left(ts,1)+"."+mid(ts,2)
   ts=str(n.mantissa[1])
   if len(ts)<8 then
      ts=string(8-len(ts),"0")+ts
   end if   
   v=v+ts
    x=val(v)
    If x = 0 Then  Return r 'Exit Function  print "Div 0":
    If x = 1 andalso ex=0 Then
      r=str2fp("1") 
      return r
   end if
   if abs(ex) and 1 then
      x=x*10
      ex-=1
   end if
   x = sqr(x) 'approximation
   v=trim(str(x))
   k=instr(v,".")
   r=str2fp(v) 
   r.exponent=ex\2+float_BIAS +1
   if len(v)>1 and k=0 then r.exponent+=1
   for k=1 to dwords
      half.mantissa[k]=0
   next
   half.mantissa[0]=50000000
   half.exponent=float_BIAS
   half.sign=0
'=====================================================================
'Newton-Raphson method
   prec=3
   for k=1 to l+1
   prec=2*prec-1
      tmp = fpdiv(n, r, prec)
      r2 = fpadd(r, tmp, prec)
        r = fpmul(r2, half, prec)
    next
    return r
End Function

function fpdiv_si(byref num As decfloat_struct, byval den As Long, byval dwords as long=NUM_DWORDS) As decfloat_struct
   if dwords>NUM_DWORDS then dwords=NUM_DWORDS
   dim as decfloat_struct fac1
    Dim As ULongint carry, remder=0
    Dim As Longint i, divisor
    Dim As Longint quotient
   
   divisor=abs(den)
   fac1=num
    If divisor = 0 Then
        'Print "error: divisor = 0"
        return fac1 'Exit function
    End If
   if divisor>99999999 Then
        'Print "error: divisor too large"
        return fac1 'Exit function
    End If
    
    For i = 0 to dwords
        quotient = fac1.mantissa[i] + remder * 100000000
        remder = quotient Mod divisor
        fac1.mantissa[i]=quotient \ divisor
    Next
    quotient = remder * 100000000
    quotient=quotient \ divisor
    carry=fac1.mantissa[0]
   
   if carry=0 then
      LSHIFT_8(fac1, dwords)
      fac1.exponent-=8
      fac1.mantissa[dwords]+=quotient
   elseif carry<10 then
      LSHIFT_7(fac1, dwords)
      fac1.exponent-=7
      fac1.mantissa[dwords]+=quotient \ 10
   elseif carry<100 then
      LSHIFT_6(fac1, dwords)
      fac1.exponent-=6
      fac1.mantissa[dwords]+=quotient \ 100
   elseif carry<1000 then
      LSHIFT_5(fac1, dwords)
      fac1.exponent-=5
      fac1.mantissa[dwords]+=quotient \ 1000
   elseif carry<10000 then
      LSHIFT_4(fac1, dwords)
      fac1.exponent-=4
      fac1.mantissa[dwords]+=quotient \ 10000
   elseif carry<100000 then
      LSHIFT_3(fac1, dwords)
      fac1.exponent-=3
      fac1.mantissa[dwords]+=quotient \ 100000
   elseif carry<1000000 then
      LSHIFT_2(fac1, dwords)
      fac1.exponent-=2
      fac1.mantissa[dwords]+=quotient \ 1000000
   elseif carry<10000000 then
      LSHIFT_1(fac1, dwords)
      fac1.exponent-=1
      fac1.mantissa[dwords]+=quotient \ 10000000
   end if  

    'NORM_FAC1(fac1)
    if den<0 then
      fac1.sign=fac1.sign Xor &h8000
   end if
   return fac1
End function

'fractional part of num
function fpfrac( byref num as decfloat_struct, byval dwords as long=NUM_DWORDS ) as decfloat_struct
   if dwords>NUM_DWORDS then dwords=NUM_DWORDS
   dim as decfloat_struct n
   n=fpfix(num)
   n=fpsub(num, n, dwords)
   return n
end function

'returns the positive of n
Function fpabs (ByRef n As decfloat_struct) As decfloat_struct
   dim as decfloat_struct x
   x=n
   x.sign=0
   return x
end function

'changes the sign of n, if n is positive then n will be negative & vice versa
Function fpneg (ByRef n As decfloat_struct) As decfloat_struct
   dim as decfloat_struct x
   x=n
   x.sign=x.sign Xor &h8000
   return x
End Function

'returns the negative of n regardless of the sign of n
function fpnegative (byref n as decfloat_struct) as decfloat_struct
   dim as decfloat_struct x
   x=n
   x.sign = &h8000
   return x
end function

Sub fmod_dec(ByRef quotient As decfloat_struct, ByRef f_mod As decfloat_struct, ByRef num As decfloat_struct, ByRef denom As decfloat_struct, ByVal dwords As Long=NUM_DWORDS)
   if dwords>NUM_DWORDS then dwords=NUM_DWORDS
   dim as decfloat_struct q, fm 'make copy in case the destination and source are the same
   fm=fpdiv(num, denom, dwords) : q=fpfix(fm)
   fm=fpsub(fm, q, dwords) : fm=fpmul(fm, denom, dwords)
   quotient=q
   f_mod=fm
end sub

function fpeps(byval dwords as long=NUM_DWORDS) as decfloat_struct
   if dwords>NUM_DWORDS then dwords=NUM_DWORDS
   dim as decfloat_struct ep
   ep=si2fp(1, dwords)
   ep.exponent=(-(NUM_DIGITS)+float_BIAS+1)
   return ep
end function

Function decfloat.toString(ByVal places As Long = NUM_DIGITS2) As String
   Function = fp2str( This, places )
End Function

Function decfloat.toString_exp( ByVal places As Long=NUM_DIGITS2 ) As String
   Function = fpfix_exp( This.dec_num, places )
End Function

Function decfloat.toString_fix( byval places as long=NUM_DIGITS2 ) As String
   Function = fpfix_rndu( This.dec_num, places )
End Function

Function decfloat.toLong ( ) As Long
   dim as double x
   x=fp2dbl(this.dec_num )
   return clng(x)
End Function

Function decfloat.toLongint ( ) As Longint
   dim as double x
   x=fp2dbl(this.dec_num )
   return CLngInt(x)
End Function

Function decfloat.toDouble ( ) As Double
   Function = fp2dbl(this.dec_num)
End Function

Constructor decfloat ( )
   this.dec_num=si2fp(0, NUM_DWORDS)
End Constructor

Constructor decfloat ( Byval rhs As Long )
   this.dec_num=si2fp( rhs, NUM_DWORDS )
End Constructor

Constructor decfloat ( Byref rhs As String )
   this.dec_num=str2fp( rhs )
End Constructor

Constructor decfloat ( Byref rhs As decfloat)
   this.dec_num.sign=rhs.dec_num.sign
   this.dec_num.exponent=rhs.dec_num.exponent
   for i as long=0 to NUM_DWORDS
      this.dec_num.mantissa[i]=rhs.dec_num.mantissa[i]
   next
End Constructor

Constructor decfloat ( Byval rhs As Longint )
   this.dec_num=si2fp( rhs, NUM_DWORDS )
End Constructor

Constructor decfloat ( Byval rhs As Integer )
   this.dec_num=si2fp( rhs, NUM_DWORDS )
End Constructor

Constructor decfloat ( Byval rhs As Double )
   this.dec_num=str2fp( str( rhs ) )
End Constructor

Destructor decfloat ( )
End Destructor

Operator decfloat.let ( Byref rhs As decfloat )
   this.dec_num.sign=rhs.dec_num.sign
   this.dec_num.exponent=rhs.dec_num.exponent
   for i as long=0 to NUM_DWORDS
      this.dec_num.mantissa[i]=rhs.dec_num.mantissa[i]
   next
End Operator

Operator decfloat.let ( Byval rhs As Long )
   this.dec_num=si2fp( rhs, NUM_DWORDS )
End Operator

Operator decfloat.let ( Byref rhs As String )
   this.dec_num=str2fp( rhs )
End Operator

Operator decfloat.Let ( Byval rhs As Longint )
   This.dec_num=si2fp( rhs, NUM_DWORDS )
End Operator

Operator decfloat.Let ( Byval rhs As Integer )
   This.dec_num=si2fp( rhs, NUM_DWORDS )
End Operator

Operator decfloat.Let ( Byval rhs As Double )
   This.dec_num=str2fp( Str(rhs) )
End Operator

Operator decfloat.Cast ( ) As String
   Operator = fp2str_exp(This.Dec_Num)
End Operator

Operator decfloat.cast ( ) As Long
   dim as double x
   x=fp2dbl(this.dec_num )
   Operator = clng(x)
End Operator

Operator decfloat.cast ( ) As Double
   Operator = fp2dbl(this.dec_num)
End Operator

'============================================================================
'' For Next for decfloat type
''
'' implicit step versions
'' 
'' In this example, we interpret implicit step
'' to mean 1
Operator decfloat.for ( )
End Operator
 
Operator decfloat.step ( )
        this.dec_num = fpadd(this.dec_num,si2fp(1, NUM_DWORDS), NUM_DWORDS) 
End Operator 
 
Operator decfloat.next ( Byref end_cond As decfloat ) As Integer
        Return fpcmp(This.dec_num, end_cond.dec_num, NUM_DWORDS)<=0
End Operator
 
 
'' explicit step versions
'' 
Operator decfloat.for ( Byref step_var As decfloat )
End Operator
 
Operator decfloat.step ( Byref step_var As decfloat )
        this.dec_num = fpadd(this.dec_num, step_var.dec_num, NUM_DWORDS)    
End Operator 
 
Operator decfloat.next ( Byref end_cond As decfloat, Byref step_var As decfloat ) As Integer
        If fpcmp(step_var.dec_num, si2fp(0, NUM_DWORDS), NUM_DWORDS) < 0 Then
                Return fpcmp(This.dec_num, end_cond.dec_num, NUM_DWORDS) >= 0
        Else
                Return fpcmp(This.dec_num, end_cond.dec_num, NUM_DWORDS) <= 0
        End If
End Operator

'============================================================================

Operator + ( Byref lhs As decfloat, Byval rhs As decfloat ) As decfloat
   Dim As decfloat result
   result.dec_num = fpadd(lhs.dec_num, rhs.dec_num, NUM_DWORDS)
   Operator = result
End Operator

Operator + ( Byref lhs As decfloat, Byval rhs As Double ) As decfloat
   Dim As decfloat result
   result.dec_num=str2fp( str(rhs) )
   result.dec_num = fpadd(lhs.dec_num, result.dec_num, NUM_DWORDS)
   Operator = result
End Operator

Operator + ( Byval lhs As Double, Byref rhs As decfloat ) As decfloat
   Dim As decfloat result
   result.dec_num=str2fp( str(lhs) )
   result.dec_num = fpadd( result.dec_num, rhs.dec_num, NUM_DWORDS)
   Operator = result
End Operator

Operator + ( Byref lhs As decfloat, Byval rhs As Longint ) As decfloat
   Dim As decfloat result
   result.dec_num=si2fp(rhs, NUM_DWORDS)
   result.dec_num = fpadd(lhs.dec_num, result.dec_num, NUM_DWORDS)
   Operator = result
End Operator

Operator + ( Byval lhs As Longint, byref rhs As decfloat  ) As decfloat
   Dim As decfloat result
   result.dec_num=si2fp(lhs, NUM_DWORDS)
   result.dec_num = fpadd(result.dec_num, rhs.dec_num, NUM_DWORDS)
   Operator = result
End Operator

Operator + (Byref lhs As decfloat, byref rhs as String) As decfloat
   dim as decfloat result
   result.dec_num =str2fp(rhs)
   result.dec_num = fpadd(lhs.dec_num, result.dec_num, NUM_DWORDS)
   Operator = result
End Operator

Operator - ( Byref rhs As decfloat ) As decfloat
   Dim As decfloat result
   result.dec_num = fpneg(rhs.dec_num)
   Operator = result
End Operator

Operator - ( Byref lhs As decfloat, Byval rhs As decfloat ) As decfloat
   Dim As decfloat result
   result.dec_num = fpsub(lhs.dec_num, rhs.dec_num, NUM_DWORDS)
   Operator = result
End Operator

Operator - ( Byref lhs As decfloat, Byval rhs As Double ) As decfloat
   Dim As decfloat result
   result.dec_num=str2fp( str(rhs) )
   result.dec_num = fpsub(lhs.dec_num, result.dec_num, NUM_DWORDS)
   Operator = result
End Operator

Operator - ( Byval lhs As Double, Byref rhs As decfloat ) As decfloat
   Dim As decfloat result
   result.dec_num=str2fp( str(lhs) )
   result.dec_num = fpsub( result.dec_num, rhs.dec_num, NUM_DWORDS)
   Operator = result
End Operator

Operator - ( Byref lhs As decfloat, Byval rhs As Longint ) As decfloat
   Dim As decfloat result
   result.dec_num=si2fp(rhs, NUM_DWORDS)
   result.dec_num = fpsub(lhs.dec_num, result.dec_num, NUM_DWORDS)
   Operator = result
End Operator

Operator - ( Byval lhs As Longint, byref rhs As decfloat  ) As decfloat
   Dim As decfloat result
   result.dec_num=si2fp(lhs, NUM_DWORDS)
   result.dec_num = fpsub(result.dec_num, rhs.dec_num, NUM_DWORDS)
   Operator = result
End Operator

Operator - (Byref lhs As decfloat, byref rhs as String) As decfloat
   dim as decfloat result
   result.dec_num =str2fp(rhs)
   result.dec_num = fpsub(lhs.dec_num, result.dec_num, NUM_DWORDS)
   Operator = result
End Operator

Operator * ( Byref lhs As decfloat, Byval rhs As decfloat ) As decfloat
   Dim As decfloat result
   result.dec_num = fpmul(lhs.dec_num, rhs.dec_num, NUM_DWORDS)
   Operator = result
End Operator

Operator * ( Byref lhs As decfloat, Byval rhs As Double ) As decfloat
   Dim As decfloat result
   result.dec_num=str2fp( str(rhs) )
   result.dec_num = fpmul(lhs.dec_num, result.dec_num, NUM_DWORDS)
   Operator = result
End Operator

Operator * ( Byval lhs As Double, Byref rhs As decfloat ) As decfloat
   Dim As decfloat result
   result.dec_num=str2fp( str(lhs) )
   result.dec_num = fpmul( result.dec_num, rhs.dec_num, NUM_DWORDS)
   Operator = result
End Operator

Operator * ( Byref lhs As decfloat, Byval rhs As Longint ) As decfloat
   Dim As decfloat result
   if abs(rhs)<100000000 then
      result.dec_num=fpmul_si(lhs.dec_num, rhs)
   else
      result.dec_num=si2fp(rhs, NUM_DWORDS)
      result.dec_num = fpmul(lhs.dec_num, result.dec_num, NUM_DWORDS)
   end if
   Operator = result
End Operator

Operator * ( Byval lhs As Longint, byref rhs As decfloat  ) As decfloat
   Dim As decfloat result
   result.dec_num=si2fp(lhs, NUM_DWORDS)
   result.dec_num = fpmul(result.dec_num, rhs.dec_num, NUM_DWORDS)
   Operator = result
End Operator

Operator * (Byref lhs As decfloat, byref rhs as String) As decfloat
   dim as decfloat result
   result.dec_num =str2fp(rhs)
   result.dec_num = fpmul(lhs.dec_num, result.dec_num, NUM_DWORDS)
   Operator = result
End Operator

Operator / ( Byref lhs As decfloat, Byval rhs As decfloat ) As decfloat
   Dim As decfloat result
   result.dec_num = fpdiv(lhs.dec_num, rhs.dec_num, NUM_DWORDS)
   Operator = result
End Operator

Operator / ( Byref lhs As decfloat, Byval rhs As Double ) As decfloat
   Dim As decfloat result
   result.dec_num=str2fp( str(rhs) )
   result.dec_num = fpdiv(lhs.dec_num, result.dec_num, NUM_DWORDS)
   Operator = result
End Operator

Operator / ( Byval lhs As Double, Byref rhs As decfloat ) As decfloat
   Dim As decfloat result
   result.dec_num=str2fp( str(lhs) )
   result.dec_num = fpdiv( result.dec_num, rhs.dec_num, NUM_DWORDS)
   Operator = result
End Operator

Operator / ( Byref lhs As decfloat, Byval rhs As Longint ) As decfloat
   Dim As decfloat result
   result.dec_num=si2fp(rhs, NUM_DWORDS)
   result.dec_num = fpdiv(lhs.dec_num, result.dec_num, NUM_DWORDS)
   Operator = result
End Operator

Operator / ( Byval lhs As Longint, byref rhs As decfloat  ) As decfloat
   Dim As decfloat result
   result.dec_num=si2fp(lhs, NUM_DWORDS)
   result.dec_num = fpdiv(result.dec_num, rhs.dec_num, NUM_DWORDS)
   Operator = result
End Operator

Operator / (Byref lhs As decfloat, byref rhs as String) As decfloat
   dim as decfloat result
   result.dec_num =str2fp(rhs)
   result.dec_num = fpdiv(lhs.dec_num, result.dec_num, NUM_DWORDS)
   Operator = result
End Operator

declare Function fplogTaylor(x As decfloat_struct, byval dwords as long=NUM_DWORDS) As decfloat_struct
declare Function fplog (x As decfloat_struct, byval dwords as long=NUM_DWORDS) As decfloat_struct
declare Function fpexp (byref x As decfloat_struct, byval dwords as long=NUM_DWORDS) As decfloat_struct
declare Function fpexp_cf(byref x as decfloat_struct, ByVal n As Integer, byval dwords as long=NUM_DWORDS) As decfloat_struct
declare function fpipow(byref x as decfloat_struct, byval e as Longint, byval dwords as long=NUM_DWORDS) as decfloat_struct
declare Function fplog_r (x As decfloat_struct, byval dwords as long=NUM_DWORDS) As decfloat_struct

Operator ^ ( Byref lhs As decfloat, Byval rhs As Longint ) As decfloat
   Dim As decfloat lhs2
   lhs2.dec_num=fpipow(lhs.dec_num, rhs, NUM_DWORDS)
   Operator = lhs2
end operator

Operator ^ ( Byval lhs As Longint, Byref rhs As decfloat ) As decfloat
   Dim As decfloat lhs2
   lhs2.dec_num=str2fp(str(lhs))
   lhs2.dec_num=fplog(lhs2.dec_num, NUM_DWORDS)
   lhs2.dec_num=fpmul(lhs2.dec_num, rhs.dec_num, NUM_DWORDS)
   lhs2.dec_num=fpexp(lhs2.dec_num, NUM_DWORDS)
   Operator = lhs2
End Operator

Operator ^ ( Byref lhs As decfloat, Byref rhs As decfloat ) As decfloat
   Dim As decfloat lhs2
   lhs2.dec_num=fplog(lhs.dec_num, NUM_DWORDS)
   lhs2.dec_num=fpmul(lhs2.dec_num, rhs.dec_num, NUM_DWORDS)
   lhs2.dec_num=fpexp(lhs2.dec_num, NUM_DWORDS)
   Operator = lhs2
End Operator

Operator ^ (Byref lhs As decfloat, byref rhs as String) As decfloat
   dim as decfloat lhs2, rhs2
   rhs2.dec_num =str2fp(rhs)
   lhs2.dec_num=fplog(lhs.dec_num, NUM_DWORDS)
   lhs2.dec_num=fpmul(lhs2.dec_num, rhs2.dec_num, NUM_DWORDS)
   lhs2.dec_num=fpexp(lhs2.dec_num, NUM_DWORDS)
   Operator = lhs2
End Operator

Operator decfloat.+= (Byref rhs As decfloat)
   this.dec_num = fpadd(this.dec_num, rhs.dec_num, NUM_DWORDS)
End Operator

Operator decfloat.+= (Byval rhs As Longint)
   Dim As decfloat result
   result.dec_num=si2fp(rhs, NUM_DWORDS)
   this.dec_num = fpadd(this.dec_num, result.dec_num, NUM_DWORDS)
End Operator

Operator decfloat.+= (Byval rhs As Double)
   Dim As decfloat result
   result.dec_num=str2fp( str(rhs) )
   this.dec_num = fpadd(this.dec_num, result.dec_num, NUM_DWORDS)
End Operator

Operator decfloat.+= (Byref rhs As String)
   Dim As decfloat result
   result.dec_num=str2fp(rhs)
   this.dec_num = fpadd(this.dec_num, result.dec_num, NUM_DWORDS)
End Operator

Operator decfloat.-= (Byref rhs As decfloat)
   this.dec_num = fpsub(this.dec_num, rhs.dec_num, NUM_DWORDS)
End Operator

Operator decfloat.-= (Byval rhs As Longint)
   Dim As decfloat result
   result.dec_num=si2fp(rhs, NUM_DWORDS)
   this.dec_num = fpsub(this.dec_num, result.dec_num, NUM_DWORDS)
End Operator

Operator decfloat.-= (Byval rhs As Double)
   Dim As decfloat result
   result.dec_num=str2fp( str(rhs) )
   this.dec_num = fpsub(this.dec_num, result.dec_num, NUM_DWORDS)
End Operator

Operator decfloat.-= (Byref rhs As String)
   Dim As decfloat result
   result.dec_num=str2fp(rhs)
   this.dec_num = fpsub(this.dec_num, result.dec_num, NUM_DWORDS)
End Operator

Operator decfloat.*= (Byref rhs As decfloat)
   this.dec_num = fpmul(this.dec_num, rhs.dec_num, NUM_DWORDS)
End Operator

Operator decfloat.*= (Byval rhs As Longint)
   Dim As decfloat result
   result.dec_num=si2fp(rhs, NUM_DWORDS)
   this.dec_num = fpmul(this.dec_num, result.dec_num, NUM_DWORDS)
End Operator

Operator decfloat.*= (Byval rhs As Double)
   Dim As decfloat result
   result.dec_num=str2fp( str(rhs) )
   this.dec_num = fpmul(this.dec_num, result.dec_num, NUM_DWORDS)
End Operator

Operator decfloat.*= (Byref rhs As String)
   Dim As decfloat result
   result.dec_num=str2fp(rhs)
   this.dec_num = fpmul(this.dec_num, result.dec_num, NUM_DWORDS)
End Operator

Operator decfloat./= (Byref rhs As decfloat)
   this.dec_num = fpdiv(this.dec_num, rhs.dec_num, NUM_DWORDS)
End Operator

Operator decfloat./= (Byval rhs As Longint)
   Dim As decfloat result
   result.dec_num=si2fp(rhs, NUM_DWORDS)
   this.dec_num = fpdiv(this.dec_num, result.dec_num, NUM_DWORDS)
End Operator

Operator decfloat./= (Byval rhs As Double)
   Dim As decfloat result
   result.dec_num=str2fp( str(rhs) )
   this.dec_num = fpdiv(this.dec_num, result.dec_num, NUM_DWORDS)
End Operator

Operator decfloat./= (Byref rhs As String)
   Dim As decfloat result
   result.dec_num=str2fp(rhs)
   this.dec_num = fpdiv(this.dec_num, result.dec_num, NUM_DWORDS)
End Operator

Operator = ( Byref lhs As decfloat, Byref rhs As decfloat ) As Long
   Operator = fpcmp(lhs.dec_num, rhs.dec_num, NUM_DWORDS)=0
End Operator

Operator < ( Byref lhs As decfloat, Byref rhs As decfloat ) As Long
   Operator = fpcmp(lhs.dec_num, rhs.dec_num, NUM_DWORDS)<0
End Operator

Operator > ( Byref lhs As decfloat, Byref rhs As decfloat ) As Long
   Operator = fpcmp(lhs.dec_num, rhs.dec_num, NUM_DWORDS)>0
End Operator

Operator <= ( Byref lhs As decfloat, Byref rhs As decfloat ) As Long
   Operator = fpcmp(lhs.dec_num, rhs.dec_num, NUM_DWORDS)<=0
End Operator

Operator >= ( Byref lhs As decfloat, Byref rhs As decfloat ) As Long
   Operator = fpcmp(lhs.dec_num, rhs.dec_num, NUM_DWORDS)>=0
End Operator

Operator <> ( Byref lhs As decfloat, Byref rhs As decfloat ) As Long
   Operator = fpcmp(lhs.dec_num, rhs.dec_num, NUM_DWORDS)<>0
End Operator

'=====================================================================

function fpipow(byref x as decfloat_struct, byval e as Longint, byval dwords as long=NUM_DWORDS) as decfloat_struct
   if dwords>NUM_DWORDS then dwords=NUM_DWORDS
   'take x to an Long power
   dim as decfloat_struct y=x
   dim as decfloat_struct z
   dim as Longint n, c=0
   dim as integer i
   
   n = abs(e)
   z.sign=0
   z.exponent=(float_BIAS+1)
   z.mantissa[0]=10000000
   for i=1 to NUM_DWORDS
      z.mantissa[i]=0
   next
   while n>0
      while (n and 1)=0
         n\=2
         y=fpmul(y, y, dwords)
         c+=1
      wend
      n-=1
      z=fpmul(y, z, dwords)
      c+=1
   wend
   if e<0 then
      z=fpinv(z, dwords)
   end if
   return z
end function

function factorial(byval n as long, byval dwords as long=NUM_DWORDS) as decfloat_struct
   if dwords>NUM_DWORDS then dwords=NUM_DWORDS
   dim as decfloat_struct f
    If n < 0 Then Return f 'Exit Function   Print "inf":
    If n = 0 or n = 1 Then
      f=si2fp(1, dwords)
      return f
   end if
   f=si2fp(2, dwords)
   if n=2 then return f
   for i as long=3 to n
      f=fpmul_si(f, i, dwords)
   next
   return f
end function

Function fplogTaylor(x As decfloat_struct, byval dwords as long=NUM_DWORDS) As decfloat_struct
   if dwords>NUM_DWORDS then dwords=NUM_DWORDS
    'taylor series
    '====================Log Guard==================
    Dim As decfloat_struct g,zero
    Dim As Integer i
    g=fpabs(x)
   zero.sign=0
   zero.exponent=0
   for i=0 to NUM_DWORDS
      zero.mantissa[i]=0
   next
    If fpcmp(g, x, dwords)<>0 Then  Return zero 'Exit Function
    If fpcmp(x, zero, dwords)=0 Then  Return zero 'Exit Function
    '=============================================
    Dim As Integer invflag
    Dim As  decfloat_struct Inv,XX,Term,Accum,strC,_x,tmp,tmp2
    Dim As decfloat_struct T,B,one,Q,two

   one.sign=0
   one.exponent=(float_BIAS+1)
   one.mantissa[0]=10000000
   two.sign=0
   two.exponent=(float_BIAS+1)
   two.mantissa[0]=20000000
   for i=1 to NUM_DWORDS
      one.mantissa[i]=0
      two.mantissa[i]=0
   next
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
        swap tmp,Accum
    Loop Until fpcmp(tmp,tmp2, dwords) = 0
    accum=fpmul_si(accum,2, dwords)
    If invflag Then
        Return fpneg(accum)
    End If
    Return accum
End Function

Function fplog (x As decfloat_struct, ByVal dwords As Long=NUM_DWORDS) As decfloat_struct
   if dwords>NUM_DWORDS then dwords=NUM_DWORDS
    '====================Log Guard==================
    Dim As decfloat_struct g, one, zero
    Dim As Integer i, factor
   zero.sign=0
   zero.exponent=0
   for i=0 to NUM_DWORDS
      zero.mantissa[i]=0
   next
   one=si2fp(1, dwords)
    g=fpabs(x)
    If fpcmp(g, x, dwords)<>0 Then  Return zero 'Exit Function
    If fpcmp(x, zero, dwords)=0 Then  Return zero 'Exit Function
    If fpcmp(x, one, dwords)=0 Then  Return zero 'Exit Function
    '=============================================
    Dim As decfloat_struct approx,ans,logx
    approx=x
    factor=4096
    approx=fpsqr(approx, dwords)
    approx=fpsqr(approx, dwords)
    approx=fpsqr(approx, dwords)
    approx=fpsqr(approx, dwords)
    approx=fpsqr(approx, dwords)
    approx=fpsqr(approx, dwords)
    approx=fpsqr(approx, dwords)
    approx=fpsqr(approx, dwords)
    approx=fpsqr(approx, dwords)
    approx=fpsqr(approx, dwords)
    approx=fpsqr(approx, dwords)
    approx=fpsqr(approx, dwords)
    logx=fplogTaylor(approx, dwords)
    ans=fpmul_si(logx, factor, dwords)
    Return ans
End Function

Function fpexp (byref x As decfloat_struct, byval dwords as long=NUM_DWORDS) As decfloat_struct
   if dwords>NUM_DWORDS then dwords=NUM_DWORDS
    'taylor series
    Dim As  decfloat_struct fac,_x,temp,accum,p,term
    dim as integer i, c
    temp=si2fp(0)
    
   fac.sign=0
   fac.exponent=(float_BIAS+1)
   fac.mantissa[0]=10000000
   for i=1 to NUM_DWORDS
      fac.mantissa[i]=0
   next
   if fpcmp(x, temp, dwords)=0 then return fac
   c=1
    _x=fpdiv_si(x, 8192, dwords) 'fpdiv_si(x, 67108864) '
    p=_x
    accum=fpadd(fac, _x, dwords) '1 + x

    Do
        c+=1
        temp=accum
        fac=fpdiv_si(fac, c, dwords)
        p=fpmul(p, _x, dwords)
        term=fpmul(p,fac, dwords)
        Accum=fpadd(temp,Term, dwords)
    Loop Until fpcmp(accum,temp, dwords) = 0
    for i=1 to 13
      accum=fpmul(accum, accum, dwords)
   next
    Return accum
End Function


Function fpexp_cf(byref x as decfloat_struct, ByVal n As Integer, byval dwords as long=NUM_DWORDS) As decfloat_struct
   if dwords>NUM_DWORDS then dwords=NUM_DWORDS

   '                       x
   '    cf =   ------------------------------
   '                         x^2
   '           2 + -------------------------
   '                           x^2
   '              6 + ----------------------
   '                             x^2
   '                 10 + ------------------
   '                               x^2
   '                     14 + --------------
   '                                 x^2
   '                          18 + ---------
   '                                   x^2
   '                              22 + -----
   '                                   26 + ...
   '           (1 + cf)
   ' exp(x) = ----------
   '           (1 - cf)
   
   Dim i As Integer
   Dim As decfloat_struct s, x1, x2, tmp, tmp2
   x1=fpdiv_si(x, 32768, dwords) ' 2^13
   x2=fpmul(x1, x1, dwords)
   s=si2fp(4 * n + 6, dwords)
   For i = n To 0 Step -1
      tmp=si2fp(4 * i + 2, dwords)
      s=fpdiv(x2, s, dwords)
      s=fpadd(s, tmp, dwords)
   Next
   s=fpdiv(x1, s, dwords)
   tmp=si2fp(1, dwords)
   tmp2=tmp
   tmp=fpadd(tmp, s, dwords)
   tmp2=fpsub(tmp2, s, dwords)
   s=fpdiv(tmp, tmp2, dwords)
    for i=1 to 15 ' s^13
      s=fpmul(s, s, dwords)
   next
   Return s
End Function

Function fplog_r (byref x As decfloat_struct, byval dwords as long=NUM_DWORDS) As decfloat_struct
   if dwords>NUM_DWORDS then dwords=NUM_DWORDS
    '====================Log Guard==================
    Dim As decfloat_struct x2, y, z, tmp
    Dim As Integer i
    dim as long ex, terms, prec, n
    dim as double t, t2
    
    tmp.sign=0
   tmp.exponent=(float_BIAS+1)
   tmp.mantissa[0]=10000000
   for i=1 to NUM_DWORDS
      tmp.mantissa[i]=0
   next
   if fpcmp(x, tmp, dwords)=0 then return x2
   x2=fpsub(x, tmp, dwords)
   n=x2.sign
   x2.sign=0
   tmp.exponent-=4
   ex=(x.exponent And &h7FFFFFFF)-float_BIAS-1
   t=x.mantissa[0]+x.mantissa[1]/100000000
   t=t/10000000
   if fpcmp(x2, tmp)<=0 then
      x2.sign=n
      y=x2
      tmp=x2
      terms=2
      n=-1
      i=0
      z=x2
      while abs(x2.exponent-z.exponent)<abs(NUMBER_OF_DIGITS-ex)
         y=fpmul(y, x2, dwords)
         z=fpdiv_si(y, terms, dwords)
         if n<0 then
            tmp=fpsub(tmp, z, dwords)
         else
            tmp=fpadd(tmp, z, dwords)
         end if
         n=-n
         terms+=1
         i+=1
      wend
      return tmp
   else
      t2=log(t)+log(10)*ex
      n=log((dwords+1)*0.5)*1.5
      'x2=str2fp(str(log(t)))
      'tmp=str2fp(str(log(10)*ex))
      'x2=fpadd(x2, tmp)
      x2=str2fp(str(t2))

      prec=3
      terms=2
      prec=2*prec-1
      y=fpexp_cf(x2, terms, prec)
      tmp=fpsub(y, x, prec)
      tmp=fpdiv(tmp, y, prec)
      x2=fpsub(x2, tmp, prec)
      if dwords>1 and dwords<3 then
         for i=1 to 1
            prec=2*prec-1
            terms=2*terms+1
            y=fpexp_cf(x2, terms, prec)
            tmp=fpsub(y, x, prec)
            tmp=fpdiv(tmp, y, prec)
            x2=fpsub(x2, tmp, prec)
         next
      elseif dwords>2 and dwords<5 then
         for i=1 to 2
            prec=2*prec-1
            terms=2*terms+1
            y=fpexp_cf(x2, terms, prec)
            tmp=fpsub(y, x, prec)
            tmp=fpdiv(tmp, y, prec)
            x2=fpsub(x2, tmp, prec)
         next
      elseif dwords>4 and dwords<10 then
         for i=1 to 3
            prec=2*prec-1
            terms=2*terms+1
            y=fpexp_cf(x2, terms, prec)
            tmp=fpsub(y, x, prec)
            tmp=fpdiv(tmp, y, prec)
            x2=fpsub(x2, tmp, prec)
         next
      elseif dwords>9 and dwords<20 then
         for i=1 to 4
            prec=2*prec-1
            terms=2*terms+1
            y=fpexp_cf(x2, terms, prec)
            tmp=fpsub(y, x, prec)
            tmp=fpdiv(tmp, y, prec)
            x2=fpsub(x2, tmp, prec)   
         next
      elseif dwords>19 and dwords<36 then
         for i=1 to 5
            prec=2*prec-1
            terms=2*terms+1
            y=fpexp_cf(x2, terms, prec)
            tmp=fpsub(y, x, prec)
            tmp=fpdiv(tmp, y, prec)
            x2=fpsub(x2, tmp, prec)   
         next
      elseif dwords>35 and dwords<71 then
         for i=1 to 6
            prec=2*prec-1
            terms=2*terms+1
            y=fpexp_cf(x2, terms, prec)
            tmp=fpsub(y, x, prec)
            tmp=fpdiv(tmp, y, prec)
            x2=fpsub(x2, tmp, prec)   
         next
      elseif dwords>70 and dwords<141 then
         for i=1 to 7
            prec=2*prec-1
            terms=2*terms+1
            y=fpexp_cf(x2, terms, prec)
            tmp=fpsub(y, x, prec)
            tmp=fpdiv(tmp, y, prec)
            x2=fpsub(x2, tmp, prec)   
         next
      elseif dwords>140 and dwords<281 then
         for i=1 to 8
            prec=2*prec-1
            terms=2*terms+1
            y=fpexp_cf(x2, terms, prec)
            tmp=fpsub(y, x, prec)
            tmp=fpdiv(tmp, y, prec)
            x2=fpsub(x2, tmp, prec)   
         next
      elseif dwords>280 and dwords<561 then
         for i=1 to 9
            prec=2*prec-1
            terms=2*terms+1
            y=fpexp_cf(x2, terms, prec)
            tmp=fpsub(y, x, prec)
            tmp=fpdiv(tmp, y, prec)
            x2=fpsub(x2, tmp, prec)   
         next
      elseif dwords>560 and dwords<1121 then
         for i=1 to 10
            prec=2*prec-1
            terms=2*terms+1
            y=fpexp_cf(x2, terms, prec)
            tmp=fpsub(y, x, prec)
            tmp=fpdiv(tmp, y, prec)
            x2=fpsub(x2, tmp, prec)   
         next
      elseif dwords>1120 then
         for i=1 to 11
            prec=2*prec-1
            terms=2*terms+1
            y=fpexp_cf(x2, terms, prec)
            tmp=fpsub(y, x, prec)
            tmp=fpdiv(tmp, y, prec)
            x2=fpsub(x2, tmp, prec)   
         next
      end if
   end if
    Return x2
End Function

function fppow ( Byref lhs As decfloat, Byref rhs As decfloat ) As decfloat
   Dim As decfloat lhs2
   lhs2.dec_num=fplog(lhs.dec_num, NUM_DWORDS)
   lhs2.dec_num=fpmul(lhs2.dec_num, rhs.dec_num, NUM_DWORDS)
   lhs2.dec_num=fpexp(lhs2.dec_num, NUM_DWORDS)
   return lhs2
End function

function fpnroot(byref x as decfloat, byval p as long, byval dwords as long=NUM_DWORDS) as decfloat
   if dwords>NUM_DWORDS then dwords=NUM_DWORDS
   dim as decfloat ry, tmp, tmp2
   dim as double t, t2
   dim as long i, ex, l, prec
   
   l=log((NUM_DIGITS+8)*0.0625)*1.5
   ex=(x.dec_num.exponent And &h7FFFFFFF)-float_BIAS-1
   t=x.dec_num.mantissa[0]+x.dec_num.mantissa[1]/100000000
   t=t/10000000
   t2=log(t)/p+log(10)*ex/p
   t2=exp(t2)
   ry=t2
   prec=3

   tmp.dec_num=fpipow(ry.dec_num,p-1, prec)
   tmp.dec_num=fpdiv(x.dec_num, tmp.dec_num, prec)
   tmp2.dec_num=fpmul_si(ry.dec_num, p-1, prec)
   tmp2.dec_num=fpadd(tmp2.dec_num, tmp.dec_num, prec)
   ry.dec_num=fpdiv_si(tmp2.dec_num, p, prec)   
   for i=1 to l
      prec=2*prec-1
      tmp.dec_num=fpipow(ry.dec_num,p-1, prec)
      tmp.dec_num=fpdiv(x.dec_num, tmp.dec_num, prec)
      tmp2.dec_num=fpmul_si(ry.dec_num, p-1, prec)
      tmp2.dec_num=fpadd(tmp2.dec_num, tmp.dec_num, prec)
      ry.dec_num=fpdiv_si(tmp2.dec_num, p, prec)
   Next
   return ry
end function

Function pi_brent_salamin (ByVal digits As ULong = NUMBER_OF_DIGITS) As decfloat_struct
    If digits > NUMBER_OF_DIGITS Then digits = NUMBER_OF_DIGITS
   
    Dim As Long limit
    Dim As decfloat_struct c0, c1, c2, c05
    Dim As decfloat_struct a, b, sum
    Dim As decfloat_struct ak, bk, ck
    Dim As decfloat_struct ab, asq
    Dim As decfloat_struct pow2, tmp
   
    limit = -digits + float_BIAS + 1
    c0=si2fp(0, digits): ak = c0: bk = c0: ab = c0: asq = c0
    c1=si2fp(1, digits): a = c1: ck = c1: pow2 = c1
    c2=si2fp(2, digits): b = c2
    c05=str2fp(".5"): sum = c05

    b=fpsqr(b, digits)
    b=fpdiv(c1, b, digits)
    While fpcmp(ck, c0, digits) <> 0 And ck.exponent > limit
        ak=fpadd(a, b, digits)
        ak=fpmul(c05, ak, digits)
        ab=fpmul(a, b, digits)
        bk=fpsqr(ab, digits)
        asq=fpmul(ak, ak, digits)
        ck=fpsub(asq, ab, digits)
        pow2=fpmul(pow2, c2, digits)
        tmp=fpmul(pow2, ck, digits)
        sum=fpsub(sum, tmp, digits)
        a = ak: b = bk
    Wend
    tmp=fpdiv(asq, sum, digits)
    tmp=fpmul(c2, tmp, digits)
    return tmp
End function

function fpsin(byref x As decfloat_struct, byval dwords As ULong = NUM_DWORDS) As decfloat_struct
   If dwords > NUM_DWORDS Then dwords = NUM_DWORDS
   
   Dim As decfloat_struct XX, Term, Accum, p, temp2, fac, x_2
   Dim As decfloat_struct pi2, circ, Ab
   Dim As decfloat pi_dec, pi2_dec
   pi_dec.dec_num = pi_brent_salamin()
   pi2_dec.dec_num     = fpadd(pi_dec.dec_num, pi_dec.dec_num)
   
   x_2  = x
   pi2  = pi_dec.dec_num
   circ = pi2_dec.dec_num
   Ab   = fpabs(x)
   If fpcmp(Ab, circ, dwords) > 0 Then
      '======== CENTRALIZE ==============
      'floor/ceil to centralize
      Dim As decfloat_struct tmp, tmp2
      
      pi2  = pi2_dec.dec_num 'got 2*pi
      tmp  = fpdiv(x_2, pi2, dwords)
      tmp2 = tmp
      tmp  = fpfix(tmp) 'int part
      tmp  = fpsub(tmp2, tmp, dwords) 'frac part
      tmp  = fpmul(tmp, pi2, dwords)
      x_2  = tmp
   End If
   
   Dim As Long lm, limit, i
   Dim As decfloat_struct factor
   lm    = dwords * 8
   limit = 1      + Int( -0.45344993886092585968 + 0.022333002852398072433 * lm + 5.0461814408333079844E -7 * lm * lm - 4.2338453039804235772E -11 * lm * lm * lm)
   if limit < 0 then limit = 0
   factor = si2fp(5, dwords)
   factor = fpipow(factor, limit, dwords)
   x_2    = fpdiv(x_2, factor, dwords) 'x_=x_/5^limit
   '==================================
   Dim As Long sign(3) : sign(3) = 1
   Dim As Long c       : c       = 1
   
   Accum = x_2
   fac   = si2fp(1, dwords)
   p     = x_2
   XX    = fpmul(x_2, x_2, dwords)
   Do
      c     = c + 2
      temp2 = Accum
      fac   = fpmul_si(fac, c * (c - 1), dwords)
      p     = fpmul(p, XX, dwords)
      Term  = fpdiv(p, fac, dwords)
      If sign(c And 3) Then
         Accum = fpsub(temp2, Term, dwords)
      Else
         Accum = fpadd(temp2, Term, dwords)
      End If
   Loop Until fpcmp(Accum, temp2, dwords) = 0
   'multiply the result by 5^limit
   
   For i = 1 To limit
      p     = fpmul(Accum, Accum, dwords)
      temp2 = fpmul(Accum, p, dwords)
      '*** sin(5*x) = 5 * sin(x) - 20 * sin(x)^3 + 16 * sin(x)^5
      Accum = fpmul_si(Accum, 5, dwords)
      Term  = fpmul_si(temp2, 20, dwords)
      XX    = fpmul_si(temp2, 16, dwords)
      XX    = fpmul(XX, p, dwords)
      Accum = fpsub(Accum, Term, dwords)
      Accum = fpadd(Accum, XX, dwords)
   Next i
   return Accum
End function

function fpcos(byref z As decfloat_struct, byval dwords As ULong = NUM_DWORDS) As decfloat_struct
   If dwords > NUM_DWORDS Then dwords = NUM_DWORDS
   Dim As decfloat_struct x_2
   Dim As decfloat pi_dec, pi_dec_half
   pi_dec.dec_num      = pi_brent_salamin()
   pi_dec_half.dec_num = fpdiv_si(pi_dec.dec_num, 2)
   x_2 = fpsub(pi_dec_half.dec_num, z, dwords)
   return fpsin(x_2, dwords)
End function


function fptan (byref z As decfloat_struct, byval dwords As ULong = NUM_DWORDS) As decfloat_struct
   If dwords > NUM_DWORDS Then dwords = NUM_DWORDS
    Dim As decfloat_struct x_2, s, c
    x_2 = z
    s = fpsin(x_2, dwords)
    x_2 = z
    c = fpcos(x_2, dwords)
    return fpdiv(s, c, dwords)
End function

function fpatn(byref x As decfloat_struct, byval dwords As ULong = NUM_DWORDS) As decfloat_struct
   If dwords > NUM_DWORDS Then dwords = NUM_DWORDS
   Dim As Long sign(3) : sign(3) = 1
   Dim As long z, c = 1
   Dim As decfloat_struct XX, Term, Accum, strC, x_2, mt, mt2, p
   Dim As decfloat_struct decnum, one, decnum2, factor
   Dim As decfloat        pi_dec
   pi_dec.dec_num = pi_brent_salamin()
   decnum2      = x
   decnum2.sign = 0
   one          = si2fp(1, dwords)
   If fpcmp(decnum2, one, dwords) = 0 Then
      decnum      = fpdiv_si(pi_dec.dec_num, 4, dwords)
      decnum.sign = x.sign
      return decnum
   End If
   decnum2.sign = x.sign
   Dim As Long limit = 16
   factor = si2fp(2 shl (limit - 1), dwords)
   For z = 1 To limit
      decnum  = fpmul(decnum2, decnum2, dwords)
      decnum  = fpadd(decnum, one, dwords)
      decnum  = fpsqr(decnum, dwords)
      decnum  = fpadd(decnum, one, dwords)
      decnum  = fpdiv(decnum2, decnum, dwords)
      decnum2 = decnum
   Next z
   
   mt  = decnum
   x_2 = decnum
   p   = decnum
   XX  = fpmul(x_2, x_2, dwords)
   Do
      c    = c + 2
      mt2  = mt
      strC = si2fp(c, dwords)
      p    = fpmul(p, XX, dwords)
      Term = fpdiv(p, strC, dwords)
      If sign(c And 3) Then
         Accum = fpsub(mt, Term, dwords)
      Else
         Accum = fpadd(mt, Term, dwords)
      End If
      Swap mt, Accum
   Loop Until fpcmp(mt, mt2, dwords) = 0
   return fpmul(factor, mt, dwords)
End function

function fpasin (byref x As decfloat_struct, byval dwords As ULong = NUM_DWORDS) As decfloat_struct
   If dwords > NUM_DWORDS Then dwords = NUM_DWORDS
    Dim As Double num
    Dim As decfloat_struct one, T, B, term1, minusone
    ' ARCSIN = ATN(x / SQR(-x * x + 1))
    '============= ARCSIN GUARD =========
    num = fp2dbl(x)
    If num > 1 Then return one
    If num < -1 Then return one
    '========================
    
    one =si2fp(1, dwords)
    minusone = si2fp(-1, dwords)
    T = x
    B = fpmul(x, x, dwords) 'x*x
    'for 1 and -1
    If fpcmp(B, one, dwords) = 0 Then
        Dim As decfloat_struct two, atn1
        two = si2fp(2, dwords)
        atn1 = fpatn(one, dwords)
        If fpcmp(x, minusone, dwords) = 0 Then
            two = fpmul(two, atn1, dwords)
            return fpmul(two, minusone, dwords)
        Else
            return fpmul(two, atn1, dwords)
        End If
    End If
    B = fpsub(one, B, dwords) '1-x*x
    B = fpsqr(B, dwords) 'sqr(1-x*x)
    term1 = fpdiv(T, B, dwords)
    return fpatn(term1, dwords)
End function

function fpacos (byref x As decfloat_struct, byval dwords As ULong = NUM_DWORDS) As decfloat_struct
   If dwords > NUM_DWORDS Then dwords = NUM_DWORDS
    Dim As decfloat_struct one, minusone, two, atn1, tail, T, B, term1, atnterm1 ',_x,temp
    Dim As Double num
    'ARCCOS = ATN(-x / SQR(-x * x + 1)) + 2 * ATN(1)
    '============= ARCCOS GUARD =========
    num = fp2dbl(x)
    If num > 1 Then return one
    If num < -1 Then return one
    '========================
    one = si2fp(1, dwords)
    minusone = si2fp(-1, dwords)
    two = si2fp(2, dwords)
    atn1 = fpatn(one, dwords)
    tail = fpmul(two, atn1, dwords) '2*atn(1)
    T = fpmul(minusone, x, dwords) '-x
    B = fpmul(x, x, dwords) 'x*x
    If fpcmp(B, one, dwords) = 0 Then
        'for 1 and -1
        If fpcmp(x, minusone, dwords) = 0 Then
            Dim As decfloat_struct four
            four = si2fp(4, dwords)
            return fpmul(four, atn1, dwords)
        Else
            return si2fp(0, dwords)
        End If
    End If
    B = fpsub(one, B, dwords) '1-x*x
    B = fpsqr(B, dwords) 'sqr(1-x*x)
    term1 = fpdiv(T, B, dwords)
    atnterm1 = fpatn(term1, dwords)
    return fpadd(atnterm1, tail, dwords)
End function

'=====================================================================
Operator Abs(Byref rhs As decfloat) As decfloat
   Dim As decfloat result
   result.dec_num=fpabs(rhs.dec_num)
   Operator = result
End Operator

Operator  Fix (Byref x As decfloat) As decfloat
   Dim As decfloat result
   result.dec_num =fpfix(x.dec_num)
   Operator = result
End Operator

Operator Frac(Byref x As decfloat) As decfloat
   Dim As decfloat result
   result.dec_num=fpfrac(x.dec_num, NUM_DWORDS)
   Operator = result
End Operator

Operator Sqr(Byref x As decfloat) As decfloat
   Dim As decfloat result
   result.dec_num=fpsqr(x.dec_num, NUM_DWORDS)
   Return result
End Operator

operator sin(byref x As decfloat) As decfloat
   Dim As decfloat result
   result.dec_num=fpsin(x.dec_num, NUM_DWORDS)
   Return result
End Operator

operator cos(byref x As decfloat) As decfloat
   Dim As decfloat result
   result.dec_num=fpcos(x.dec_num, NUM_DWORDS)
   Return result
End Operator

operator tan(byref x As decfloat) As decfloat
   Dim As decfloat result
   result.dec_num=fptan(x.dec_num, NUM_DWORDS)
   Return result
End Operator

operator asin(byref x As decfloat) As decfloat
   Dim As decfloat result
   result.dec_num=fpasin(x.dec_num, NUM_DWORDS)
   Return result
End Operator

operator acos(byref x As decfloat) As decfloat
   Dim As decfloat result
   result.dec_num=fpacos(x.dec_num, NUM_DWORDS)
   Return result
End Operator

operator atn(byref x As decfloat) As decfloat
   Dim As decfloat result
   result.dec_num=fpatn(x.dec_num, NUM_DWORDS)
   Return result
End Operator

operator log(byref x As decfloat) As decfloat
   Dim As decfloat result
   result.dec_num=fplog(x.dec_num, NUM_DWORDS)
   Return result
End Operator

operator exp(byref x As decfloat) As decfloat
   Dim As decfloat result
   result.dec_num=fpexp(x.dec_num, NUM_DWORDS)
   Return result
End Operator

function factorial_inv(byval n as ulong) as decfloat_struct
   dim as decfloat_struct f
   f.mantissa[0]=10000000
   f.exponent=0+float_BIAS+1
   for i as long=1 to n
      f=fpdiv_si(f, i)
   next
   return f
end function
