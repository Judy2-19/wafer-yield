-- 与工程师实际建表语句对齐（summaryhead / summarydetail）
-- 字段来自设备库；本 Web 系统只处理 summarydetail.WaveLength = 1311
--
-- 用法：MySQL Workbench 执行，或双击 创建数据库.bat

CREATE DATABASE IF NOT EXISTS mg_nano
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_unicode_ci;

USE mg_nano;

CREATE TABLE IF NOT EXISTS `summaryhead` (
  `ID` bigint(64) NOT NULL,
  `LoginUser` varchar(45) DEFAULT NULL,
  `ProberName` varchar(45) DEFAULT NULL,
  `Wafer` varchar(45) DEFAULT NULL,
  `Shot` varchar(45) DEFAULT NULL,
  `SN` varchar(45) DEFAULT NULL,
  `CreateTime` varchar(45) DEFAULT NULL,
  PRIMARY KEY (`ID`),
  KEY `idx_Wafer` (`Wafer`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `summarydetail` (
  `ID` bigint(64) NOT NULL,
  `HeadID` bigint(64) DEFAULT NULL,
  `Category` varchar(45) DEFAULT NULL,
  `WaveLength` varchar(45) DEFAULT NULL,
  `Chnl` varchar(45) DEFAULT NULL,
  `CreateTime` varchar(45) DEFAULT NULL,
  `ItemName` varchar(45) DEFAULT NULL,
  `ItemUnit` varchar(45) DEFAULT NULL,
  `ItemValue` double DEFAULT NULL,
  `Level` varchar(45) DEFAULT NULL,
  PRIMARY KEY (`ID`),
  KEY `idx_HeadID` (`HeadID`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
