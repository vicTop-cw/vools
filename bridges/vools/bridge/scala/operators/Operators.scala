package com.example.operators

/**
 * Scala 隐式双元操作符库：提供函数组合与管道操作的中缀操作符。
 *
 * 操作符分为两大类：
 * - 函|函（18个）：左侧与右侧均为函数，组合后产生新函数。
 * - 数|函（12个）：左侧为值或可迭代对象，右侧为函数，将数据传入函数处理。
 *
 * 使用方式：
 *   import com.example.operators.Operators._
 *
 * 函|函操作符：
 *   #> / <#    - 无参函数 -> 单参函数
 *   #>> / <<#  - 无参函数 -> 双参函数
 *   *#> / <#*  - 无参函数 -> 解包应用
 *   ~> / <~    - 单参函数 -> 单参函数（函数复合）
 *   ~>> / <<~  - 单参函数 -> 双参函数
 *   *~> / <~*  - 单参函数 -> 解包应用
 *   ~~> / <~~  - 双参函数 -> 单参函数
 *   *~~> / <~~*- 双参函数 -> 解包应用
 *   ~~>> / <<~~- 双参函数 -> 双参函数
 *
 * 数|函操作符：
 *   |> / <|    - 值 -> 函数（函数应用）
 *   |>> / <<|  - 可迭代对象 -> map
 *   |?> / <|?  - 可迭代对象 -> filter
 *   |*> / <*|  - 可迭代对象 -> flatMap
 *   |&> / <&|  - 可迭代对象 -> reduce
 *   |@> / <@|  - 可迭代对象 -> fold（柯里化）
 */
object Operators {

  sealed trait SeqMarker
  implicit object SeqMarker extends SeqMarker

  sealed trait Tuple2Marker
  implicit object Tuple2Marker extends Tuple2Marker

  sealed trait Tuple3Marker
  implicit object Tuple3Marker extends Tuple3Marker

  sealed trait Tuple4Marker
  implicit object Tuple4Marker extends Tuple4Marker

  sealed trait Tuple5Marker
  implicit object Tuple5Marker extends Tuple5Marker

  implicit class ZeroArgToSingleArgForward[A](f: () => A) {
    def #>[B](g: A => B): () => B = () => g(f())
  }

  implicit class ZeroArgToSingleArgReverse[A, B](g: A => B) {
    def <#(f: () => A): () => B = () => g(f())
  }

  implicit class ZeroArgToTwoArgForward[A](f: () => A) {
    def #>>[B, C](g: (A, B) => C): B => C = b => g(f(), b)
  }

  implicit class ZeroArgToTwoArgReverse[A, B, C](g: (A, B) => C) {
    def <<#(f: () => A): B => C = b => g(f(), b)
  }

  implicit class ZeroArgUnpackSeqForward[A](f: () => Seq[A]) {
    def *#>[B](g: A => B): () => B = () => g(f().head)
    def *#>[B](g: (A, A) => B): A => B = a2 => g(f().head, a2)
    def *#>[B](g: (A, A, A) => B): (A, A) => B = (a2, a3) => g(f().head, a2, a3)
    def *#>[B](g: (A, A, A, A) => B): (A, A, A) => B = (a2, a3, a4) => g(f().head, a2, a3, a4)
    def *#>[B](g: (A, A, A, A, A) => B): (A, A, A, A) => B = (a2, a3, a4, a5) => g(f().head, a2, a3, a4, a5)
  }

  implicit class ZeroArgUnpackTuple2Forward[A](f: () => (A, A)) {
    def *#>[B](g: (A, A) => B): () => B = () => { val t = f(); g(t._1, t._2) }
    def *#>[B](g: (A, A, A) => B): A => B = a3 => { val t = f(); g(t._1, t._2, a3) }
    def *#>[B](g: (A, A, A, A) => B): (A, A) => B = (a3, a4) => { val t = f(); g(t._1, t._2, a3, a4) }
    def *#>[B](g: (A, A, A, A, A) => B): (A, A, A) => B = (a3, a4, a5) => { val t = f(); g(t._1, t._2, a3, a4, a5) }
  }

  implicit class ZeroArgUnpackTuple3Forward[A](f: () => (A, A, A)) {
    def *#>[B](g: (A, A, A) => B): () => B = () => { val t = f(); g(t._1, t._2, t._3) }
    def *#>[B](g: (A, A, A, A) => B): A => B = a4 => { val t = f(); g(t._1, t._2, t._3, a4) }
    def *#>[B](g: (A, A, A, A, A) => B): (A, A) => B = (a4, a5) => { val t = f(); g(t._1, t._2, t._3, a4, a5) }
  }

  implicit class ZeroArgUnpackTuple4Forward[A](f: () => (A, A, A, A)) {
    def *#>[B](g: (A, A, A, A) => B): () => B = () => { val t = f(); g(t._1, t._2, t._3, t._4) }
    def *#>[B](g: (A, A, A, A, A) => B): A => B = a5 => { val t = f(); g(t._1, t._2, t._3, t._4, a5) }
  }

  implicit class ZeroArgUnpackTuple5Forward[A](f: () => (A, A, A, A, A)) {
    def *#>[B](g: (A, A, A, A, A) => B): () => B = () => { val t = f(); g(t._1, t._2, t._3, t._4, t._5) }
  }

  implicit class ZeroArgUnpackReverse1[A, B](g: A => B) {
    def <#*(f: () => Seq[A])(implicit ev: SeqMarker): () => B = () => g(f().head)
    def <#*(f: () => (A, A))(implicit ev: Tuple2Marker): () => B = () => { val t = f(); g(t._1) }
    def <#*(f: () => (A, A, A))(implicit ev: Tuple3Marker): () => B = () => { val t = f(); g(t._1) }
    def <#*(f: () => (A, A, A, A))(implicit ev: Tuple4Marker): () => B = () => { val t = f(); g(t._1) }
    def <#*(f: () => (A, A, A, A, A))(implicit ev: Tuple5Marker): () => B = () => { val t = f(); g(t._1) }
  }

  implicit class ZeroArgUnpackReverse2[A, B](g: (A, A) => B) {
    def <#*(f: () => Seq[A])(implicit ev: SeqMarker): A => B = a2 => g(f().head, a2)
    def <#*(f: () => (A, A))(implicit ev: Tuple2Marker): () => B = () => { val t = f(); g(t._1, t._2) }
    def <#*(f: () => (A, A, A))(implicit ev: Tuple3Marker): A => B = a3 => { val t = f(); g(t._1, t._2) }
    def <#*(f: () => (A, A, A, A))(implicit ev: Tuple4Marker): A => B = a4 => { val t = f(); g(t._1, t._2) }
    def <#*(f: () => (A, A, A, A, A))(implicit ev: Tuple5Marker): A => B = a5 => { val t = f(); g(t._1, t._2) }
  }

  implicit class ZeroArgUnpackReverse3[A, B](g: (A, A, A) => B) {
    def <#*(f: () => Seq[A])(implicit ev: SeqMarker): (A, A) => B = (a2, a3) => g(f().head, a2, a3)
    def <#*(f: () => (A, A))(implicit ev: Tuple2Marker): A => B = a3 => { val t = f(); g(t._1, t._2, a3) }
    def <#*(f: () => (A, A, A))(implicit ev: Tuple3Marker): () => B = () => { val t = f(); g(t._1, t._2, t._3) }
    def <#*(f: () => (A, A, A, A))(implicit ev: Tuple4Marker): A => B = a4 => { val t = f(); g(t._1, t._2, t._3) }
    def <#*(f: () => (A, A, A, A, A))(implicit ev: Tuple5Marker): A => B = a5 => { val t = f(); g(t._1, t._2, t._3) }
  }

  implicit class ZeroArgUnpackReverse4[A, B](g: (A, A, A, A) => B) {
    def <#*(f: () => Seq[A])(implicit ev: SeqMarker): (A, A, A) => B = (a2, a3, a4) => g(f().head, a2, a3, a4)
    def <#*(f: () => (A, A))(implicit ev: Tuple2Marker): (A, A) => B = (a3, a4) => { val t = f(); g(t._1, t._2, a3, a4) }
    def <#*(f: () => (A, A, A))(implicit ev: Tuple3Marker): A => B = a4 => { val t = f(); g(t._1, t._2, t._3, a4) }
    def <#*(f: () => (A, A, A, A))(implicit ev: Tuple4Marker): () => B = () => { val t = f(); g(t._1, t._2, t._3, t._4) }
    def <#*(f: () => (A, A, A, A, A))(implicit ev: Tuple5Marker): A => B = a5 => { val t = f(); g(t._1, t._2, t._3, t._4) }
  }

  implicit class ZeroArgUnpackReverse5[A, B](g: (A, A, A, A, A) => B) {
    def <#*(f: () => Seq[A])(implicit ev: SeqMarker): (A, A, A, A) => B = (a2, a3, a4, a5) => g(f().head, a2, a3, a4, a5)
    def <#*(f: () => (A, A))(implicit ev: Tuple2Marker): (A, A, A) => B = (a3, a4, a5) => { val t = f(); g(t._1, t._2, a3, a4, a5) }
    def <#*(f: () => (A, A, A))(implicit ev: Tuple3Marker): (A, A) => B = (a4, a5) => { val t = f(); g(t._1, t._2, t._3, a4, a5) }
    def <#*(f: () => (A, A, A, A))(implicit ev: Tuple4Marker): A => B = a5 => { val t = f(); g(t._1, t._2, t._3, t._4, a5) }
    def <#*(f: () => (A, A, A, A, A))(implicit ev: Tuple5Marker): () => B = () => { val t = f(); g(t._1, t._2, t._3, t._4, t._5) }
  }

  implicit class SingleArgComposeForward[D, A](f: D => A) {
    def ~>[B](g: A => B): D => B = d => g(f(d))
  }

  implicit class SingleArgComposeReverse[A, B](g: A => B) {
    def <~[D](f: D => A): D => B = d => g(f(d))
  }

  implicit class SingleArgToTwoArgForward[D, A](f: D => A) {
    def ~>>[B, C](g: (A, B) => C): (D, B) => C = (d, b) => g(f(d), b)
  }

  implicit class SingleArgToTwoArgReverse[A, B, C](g: (A, B) => C) {
    def <<~[D](f: D => A): (D, B) => C = (d, b) => g(f(d), b)
  }

  implicit class SingleArgUnpackSeqForward[D, A](f: D => Seq[A]) {
    def *~>[B](g: A => B): D => B = d => g(f(d).head)
    def *~>[B](g: (A, A) => B): (D, A) => B = (d, a2) => g(f(d).head, a2)
    def *~>[B](g: (A, A, A) => B): (D, A, A) => B = (d, a2, a3) => g(f(d).head, a2, a3)
    def *~>[B](g: (A, A, A, A) => B): (D, A, A, A) => B = (d, a2, a3, a4) => g(f(d).head, a2, a3, a4)
    def *~>[B](g: (A, A, A, A, A) => B): (D, A, A, A, A) => B = (d, a2, a3, a4, a5) => g(f(d).head, a2, a3, a4, a5)
  }

  implicit class SingleArgUnpackTuple2Forward[D, A](f: D => (A, A)) {
    def *~>[B](g: (A, A) => B): D => B = d => { val t = f(d); g(t._1, t._2) }
    def *~>[B](g: (A, A, A) => B): (D, A) => B = (d, a3) => { val t = f(d); g(t._1, t._2, a3) }
    def *~>[B](g: (A, A, A, A) => B): (D, A, A) => B = (d, a3, a4) => { val t = f(d); g(t._1, t._2, a3, a4) }
    def *~>[B](g: (A, A, A, A, A) => B): (D, A, A, A) => B = (d, a3, a4, a5) => { val t = f(d); g(t._1, t._2, a3, a4, a5) }
  }

  implicit class SingleArgUnpackTuple3Forward[D, A](f: D => (A, A, A)) {
    def *~>[B](g: (A, A, A) => B): D => B = d => { val t = f(d); g(t._1, t._2, t._3) }
    def *~>[B](g: (A, A, A, A) => B): (D, A) => B = (d, a4) => { val t = f(d); g(t._1, t._2, t._3, a4) }
    def *~>[B](g: (A, A, A, A, A) => B): (D, A, A) => B = (d, a4, a5) => { val t = f(d); g(t._1, t._2, t._3, a4, a5) }
  }

  implicit class SingleArgUnpackTuple4Forward[D, A](f: D => (A, A, A, A)) {
    def *~>[B](g: (A, A, A, A) => B): D => B = d => { val t = f(d); g(t._1, t._2, t._3, t._4) }
    def *~>[B](g: (A, A, A, A, A) => B): (D, A) => B = (d, a5) => { val t = f(d); g(t._1, t._2, t._3, t._4, a5) }
  }

  implicit class SingleArgUnpackTuple5Forward[D, A](f: D => (A, A, A, A, A)) {
    def *~>[B](g: (A, A, A, A, A) => B): D => B = d => { val t = f(d); g(t._1, t._2, t._3, t._4, t._5) }
  }

  implicit class SingleArgUnpackReverse1[A, B](g: A => B) {
    def <~*[D](f: D => Seq[A])(implicit ev: SeqMarker): D => B = d => g(f(d).head)
    def <~*[D](f: D => (A, A))(implicit ev: Tuple2Marker): D => B = d => { val t = f(d); g(t._1) }
    def <~*[D](f: D => (A, A, A))(implicit ev: Tuple3Marker): D => B = d => { val t = f(d); g(t._1) }
    def <~*[D](f: D => (A, A, A, A))(implicit ev: Tuple4Marker): D => B = d => { val t = f(d); g(t._1) }
    def <~*[D](f: D => (A, A, A, A, A))(implicit ev: Tuple5Marker): D => B = d => { val t = f(d); g(t._1) }
  }

  implicit class SingleArgUnpackReverse2[A, B](g: (A, A) => B) {
    def <~*[D](f: D => Seq[A])(implicit ev: SeqMarker): (D, A) => B = (d, a2) => g(f(d).head, a2)
    def <~*[D](f: D => (A, A))(implicit ev: Tuple2Marker): D => B = d => { val t = f(d); g(t._1, t._2) }
    def <~*[D](f: D => (A, A, A))(implicit ev: Tuple3Marker): (D, A) => B = (d, a3) => { val t = f(d); g(t._1, t._2) }
    def <~*[D](f: D => (A, A, A, A))(implicit ev: Tuple4Marker): (D, A) => B = (d, a4) => { val t = f(d); g(t._1, t._2) }
    def <~*[D](f: D => (A, A, A, A, A))(implicit ev: Tuple5Marker): (D, A) => B = (d, a5) => { val t = f(d); g(t._1, t._2) }
  }

  implicit class SingleArgUnpackReverse3[A, B](g: (A, A, A) => B) {
    def <~*[D](f: D => Seq[A])(implicit ev: SeqMarker): (D, A, A) => B = (d, a2, a3) => g(f(d).head, a2, a3)
    def <~*[D](f: D => (A, A))(implicit ev: Tuple2Marker): (D, A) => B = (d, a3) => { val t = f(d); g(t._1, t._2, a3) }
    def <~*[D](f: D => (A, A, A))(implicit ev: Tuple3Marker): D => B = d => { val t = f(d); g(t._1, t._2, t._3) }
    def <~*[D](f: D => (A, A, A, A))(implicit ev: Tuple4Marker): (D, A) => B = (d, a4) => { val t = f(d); g(t._1, t._2, t._3) }
    def <~*[D](f: D => (A, A, A, A, A))(implicit ev: Tuple5Marker): (D, A) => B = (d, a5) => { val t = f(d); g(t._1, t._2, t._3) }
  }

  implicit class SingleArgUnpackReverse4[A, B](g: (A, A, A, A) => B) {
    def <~*[D](f: D => Seq[A])(implicit ev: SeqMarker): (D, A, A, A) => B = (d, a2, a3, a4) => g(f(d).head, a2, a3, a4)
    def <~*[D](f: D => (A, A))(implicit ev: Tuple2Marker): (D, A, A) => B = (d, a3, a4) => { val t = f(d); g(t._1, t._2, a3, a4) }
    def <~*[D](f: D => (A, A, A))(implicit ev: Tuple3Marker): (D, A) => B = (d, a4) => { val t = f(d); g(t._1, t._2, t._3, a4) }
    def <~*[D](f: D => (A, A, A, A))(implicit ev: Tuple4Marker): D => B = d => { val t = f(d); g(t._1, t._2, t._3, t._4) }
    def <~*[D](f: D => (A, A, A, A, A))(implicit ev: Tuple5Marker): (D, A) => B = (d, a5) => { val t = f(d); g(t._1, t._2, t._3, t._4) }
  }

  implicit class SingleArgUnpackReverse5[A, B](g: (A, A, A, A, A) => B) {
    def <~*[D](f: D => Seq[A])(implicit ev: SeqMarker): (D, A, A, A, A) => B = (d, a2, a3, a4, a5) => g(f(d).head, a2, a3, a4, a5)
    def <~*[D](f: D => (A, A))(implicit ev: Tuple2Marker): (D, A, A, A) => B = (d, a3, a4, a5) => { val t = f(d); g(t._1, t._2, a3, a4, a5) }
    def <~*[D](f: D => (A, A, A))(implicit ev: Tuple3Marker): (D, A, A) => B = (d, a4, a5) => { val t = f(d); g(t._1, t._2, t._3, a4, a5) }
    def <~*[D](f: D => (A, A, A, A))(implicit ev: Tuple4Marker): (D, A) => B = (d, a5) => { val t = f(d); g(t._1, t._2, t._3, t._4, a5) }
    def <~*[D](f: D => (A, A, A, A, A))(implicit ev: Tuple5Marker): D => B = d => { val t = f(d); g(t._1, t._2, t._3, t._4, t._5) }
  }

  implicit class TwoArgComposeForward[D, F, A](f: (D, F) => A) {
    def ~~>[B](g: A => B): (D, F) => B = (d, f0) => g(f(d, f0))
  }

  implicit class TwoArgComposeReverse[A, B](g: A => B) {
    def <~~[D, F](f: (D, F) => A): (D, F) => B = (d, f0) => g(f(d, f0))
  }

  implicit class TwoArgUnpackSeqForward[D, F, A](f: (D, F) => Seq[A]) {
    def *~~>[B](g: A => B): (D, F) => B = (d, f0) => g(f(d, f0).head)
    def *~~>[B](g: (A, A) => B): (D, F, A) => B = (d, f0, a2) => g(f(d, f0).head, a2)
    def *~~>[B](g: (A, A, A) => B): (D, F, A, A) => B = (d, f0, a2, a3) => g(f(d, f0).head, a2, a3)
    def *~~>[B](g: (A, A, A, A) => B): (D, F, A, A, A) => B = (d, f0, a2, a3, a4) => g(f(d, f0).head, a2, a3, a4)
    def *~~>[B](g: (A, A, A, A, A) => B): (D, F, A, A, A, A) => B = (d, f0, a2, a3, a4, a5) => g(f(d, f0).head, a2, a3, a4, a5)
  }

  implicit class TwoArgUnpackTuple2Forward[D, F, A](f: (D, F) => (A, A)) {
    def *~~>[B](g: (A, A) => B): (D, F) => B = (d, f0) => { val t = f(d, f0); g(t._1, t._2) }
    def *~~>[B](g: (A, A, A) => B): (D, F, A) => B = (d, f0, a3) => { val t = f(d, f0); g(t._1, t._2, a3) }
    def *~~>[B](g: (A, A, A, A) => B): (D, F, A, A) => B = (d, f0, a3, a4) => { val t = f(d, f0); g(t._1, t._2, a3, a4) }
    def *~~>[B](g: (A, A, A, A, A) => B): (D, F, A, A, A) => B = (d, f0, a3, a4, a5) => { val t = f(d, f0); g(t._1, t._2, a3, a4, a5) }
  }

  implicit class TwoArgUnpackTuple3Forward[D, F, A](f: (D, F) => (A, A, A)) {
    def *~~>[B](g: (A, A, A) => B): (D, F) => B = (d, f0) => { val t = f(d, f0); g(t._1, t._2, t._3) }
    def *~~>[B](g: (A, A, A, A) => B): (D, F, A) => B = (d, f0, a4) => { val t = f(d, f0); g(t._1, t._2, t._3, a4) }
    def *~~>[B](g: (A, A, A, A, A) => B): (D, F, A, A) => B = (d, f0, a4, a5) => { val t = f(d, f0); g(t._1, t._2, t._3, a4, a5) }
  }

  implicit class TwoArgUnpackTuple4Forward[D, F, A](f: (D, F) => (A, A, A, A)) {
    def *~~>[B](g: (A, A, A, A) => B): (D, F) => B = (d, f0) => { val t = f(d, f0); g(t._1, t._2, t._3, t._4) }
    def *~~>[B](g: (A, A, A, A, A) => B): (D, F, A) => B = (d, f0, a5) => { val t = f(d, f0); g(t._1, t._2, t._3, t._4, a5) }
  }

  implicit class TwoArgUnpackTuple5Forward[D, F, A](f: (D, F) => (A, A, A, A, A)) {
    def *~~>[B](g: (A, A, A, A, A) => B): (D, F) => B = (d, f0) => { val t = f(d, f0); g(t._1, t._2, t._3, t._4, t._5) }
  }

  implicit class TwoArgUnpackReverse1[A, B](g: A => B) {
    def <~~*[D, F](f: (D, F) => Seq[A])(implicit ev: SeqMarker): (D, F) => B = (d, f0) => g(f(d, f0).head)
    def <~~*[D, F](f: (D, F) => (A, A))(implicit ev: Tuple2Marker): (D, F) => B = (d, f0) => { val t = f(d, f0); g(t._1) }
    def <~~*[D, F](f: (D, F) => (A, A, A))(implicit ev: Tuple3Marker): (D, F) => B = (d, f0) => { val t = f(d, f0); g(t._1) }
    def <~~*[D, F](f: (D, F) => (A, A, A, A))(implicit ev: Tuple4Marker): (D, F) => B = (d, f0) => { val t = f(d, f0); g(t._1) }
    def <~~*[D, F](f: (D, F) => (A, A, A, A, A))(implicit ev: Tuple5Marker): (D, F) => B = (d, f0) => { val t = f(d, f0); g(t._1) }
  }

  implicit class TwoArgUnpackReverse2[A, B](g: (A, A) => B) {
    def <~~*[D, F](f: (D, F) => Seq[A])(implicit ev: SeqMarker): (D, F, A) => B = (d, f0, a2) => g(f(d, f0).head, a2)
    def <~~*[D, F](f: (D, F) => (A, A))(implicit ev: Tuple2Marker): (D, F) => B = (d, f0) => { val t = f(d, f0); g(t._1, t._2) }
    def <~~*[D, F](f: (D, F) => (A, A, A))(implicit ev: Tuple3Marker): (D, F, A) => B = (d, f0, a3) => { val t = f(d, f0); g(t._1, t._2) }
    def <~~*[D, F](f: (D, F) => (A, A, A, A))(implicit ev: Tuple4Marker): (D, F, A) => B = (d, f0, a4) => { val t = f(d, f0); g(t._1, t._2) }
    def <~~*[D, F](f: (D, F) => (A, A, A, A, A))(implicit ev: Tuple5Marker): (D, F, A) => B = (d, f0, a5) => { val t = f(d, f0); g(t._1, t._2) }
  }

  implicit class TwoArgUnpackReverse3[A, B](g: (A, A, A) => B) {
    def <~~*[D, F](f: (D, F) => Seq[A])(implicit ev: SeqMarker): (D, F, A, A) => B = (d, f0, a2, a3) => g(f(d, f0).head, a2, a3)
    def <~~*[D, F](f: (D, F) => (A, A))(implicit ev: Tuple2Marker): (D, F, A) => B = (d, f0, a3) => { val t = f(d, f0); g(t._1, t._2, a3) }
    def <~~*[D, F](f: (D, F) => (A, A, A))(implicit ev: Tuple3Marker): (D, F) => B = (d, f0) => { val t = f(d, f0); g(t._1, t._2, t._3) }
    def <~~*[D, F](f: (D, F) => (A, A, A, A))(implicit ev: Tuple4Marker): (D, F, A) => B = (d, f0, a4) => { val t = f(d, f0); g(t._1, t._2, t._3) }
    def <~~*[D, F](f: (D, F) => (A, A, A, A, A))(implicit ev: Tuple5Marker): (D, F, A) => B = (d, f0, a5) => { val t = f(d, f0); g(t._1, t._2, t._3) }
  }

  implicit class TwoArgUnpackReverse4[A, B](g: (A, A, A, A) => B) {
    def <~~*[D, F](f: (D, F) => Seq[A])(implicit ev: SeqMarker): (D, F, A, A, A) => B = (d, f0, a2, a3, a4) => g(f(d, f0).head, a2, a3, a4)
    def <~~*[D, F](f: (D, F) => (A, A))(implicit ev: Tuple2Marker): (D, F, A, A) => B = (d, f0, a3, a4) => { val t = f(d, f0); g(t._1, t._2, a3, a4) }
    def <~~*[D, F](f: (D, F) => (A, A, A))(implicit ev: Tuple3Marker): (D, F, A) => B = (d, f0, a4) => { val t = f(d, f0); g(t._1, t._2, t._3, a4) }
    def <~~*[D, F](f: (D, F) => (A, A, A, A))(implicit ev: Tuple4Marker): (D, F) => B = (d, f0) => { val t = f(d, f0); g(t._1, t._2, t._3, t._4) }
    def <~~*[D, F](f: (D, F) => (A, A, A, A, A))(implicit ev: Tuple5Marker): (D, F, A) => B = (d, f0, a5) => { val t = f(d, f0); g(t._1, t._2, t._3, t._4) }
  }

  implicit class TwoArgUnpackReverse5[A, B](g: (A, A, A, A, A) => B) {
    def <~~*[D, F](f: (D, F) => Seq[A])(implicit ev: SeqMarker): (D, F, A, A, A, A) => B = (d, f0, a2, a3, a4, a5) => g(f(d, f0).head, a2, a3, a4, a5)
    def <~~*[D, F](f: (D, F) => (A, A))(implicit ev: Tuple2Marker): (D, F, A, A, A) => B = (d, f0, a3, a4, a5) => { val t = f(d, f0); g(t._1, t._2, a3, a4, a5) }
    def <~~*[D, F](f: (D, F) => (A, A, A))(implicit ev: Tuple3Marker): (D, F, A, A) => B = (d, f0, a4, a5) => { val t = f(d, f0); g(t._1, t._2, t._3, a4, a5) }
    def <~~*[D, F](f: (D, F) => (A, A, A, A))(implicit ev: Tuple4Marker): (D, F, A) => B = (d, f0, a5) => { val t = f(d, f0); g(t._1, t._2, t._3, t._4, a5) }
    def <~~*[D, F](f: (D, F) => (A, A, A, A, A))(implicit ev: Tuple5Marker): (D, F) => B = (d, f0) => { val t = f(d, f0); g(t._1, t._2, t._3, t._4, t._5) }
  }

  implicit class TwoArgToTwoArgForward[D, F, A](f: (D, F) => A) {
    def ~~>>[B, C](g: (A, B) => C): (D, F, B) => C = (d, f0, b) => g(f(d, f0), b)
  }

  implicit class TwoArgToTwoArgReverse[A, B, C](g: (A, B) => C) {
    def <<~~[D, F](f: (D, F) => A): (D, F, B) => C = (d, f0, b) => g(f(d, f0), b)
  }

  implicit class ValuePipeForward[A](a: A) {
    def |>[B](f: A => B): B = f(a)
  }

  implicit class ValuePipeReverse[A, B](f: A => B) {
    def <|(a: A): B = f(a)
  }

  implicit class IterableMapPipeForward[A](xs: Iterable[A]) {
    def |>>[B](f: A => B): Iterable[B] = xs.map(f)
  }

  implicit class IterableMapPipeReverse[A, B](f: A => B) {
    def <<|(xs: Iterable[A]): Iterable[B] = xs.map(f)
  }

  implicit class IterableFilterPipeForward[A](xs: Iterable[A]) {
    def |?>(f: A => Boolean): Iterable[A] = xs.filter(f)
  }

  implicit class IterableFilterPipeReverse[A](f: A => Boolean) {
    def <|?(xs: Iterable[A]): Iterable[A] = xs.filter(f)
  }

  implicit class IterableFlatMapPipeForward[A](xs: Iterable[Iterable[A]]) {
    def |*>[B](f: A => B): Iterable[B] = xs.flatMap(_.map(f))
  }

  implicit class IterableFlatMapPipeReverse[A, B](f: A => B) {
    def <*|(xs: Iterable[Iterable[A]]): Iterable[B] = xs.flatMap(_.map(f))
  }

  implicit class IterableReducePipeForward[A](xs: Iterable[A]) {
    def |&>(op: (A, A) => A): A = xs.reduce(op)
  }

  implicit class IterableReducePipeReverse[A](op: (A, A) => A) {
    def <&|(xs: Iterable[A]): A = xs.reduce(op)
  }

  implicit class IterableFoldPipeForward[A](xs: Iterable[A]) {
    def |@>[G](folder: G => (G, A) => G): G => G = init => xs.foldLeft(init)(folder(init))
  }

  implicit class IterableFoldPipeReverse[A, G](folder: G => (G, A) => G) {
    def <@|(xs: Iterable[A]): G => G = init => xs.foldLeft(init)(folder(init))
  }

}
