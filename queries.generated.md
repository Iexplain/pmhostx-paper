## 检索式全文

以下由 `data/queries.json` 生成，勿手工编辑。

```text
A_metatrans_host
(metatranscriptomic*[tiab] OR metatranscriptom*[tiab]) AND ("host response"[tiab] OR "host gene expression"[tiab] OR "host transcriptom*"[tiab] OR "human host"[tiab] OR "host-pathogen"[tiab])

B_mngs_hostresp
("metagenomic next-generation sequencing"[tiab] OR mNGS[tiab] OR "metagenomic sequencing"[tiab] OR "metagenomics"[tiab]) AND ("host response"[tiab] OR "host gene expression"[tiab] OR "host transcriptom*"[tiab] OR "host RNA"[tiab])

C_csf_host
("cerebrospinal fluid"[tiab]) AND (transcriptom*[tiab] OR "host response"[tiab] OR "gene expression"[tiab] OR "RNA-seq"[tiab] OR "RNA sequencing"[tiab])

D_septicyte_genes
(SeptiCyte[tiab] OR CEACAM4[tiab] OR PLAC8[tiab] OR PLA2G7[tiab] OR "LAMP1"[tiab]) AND (sepsis[tiab] OR infection[tiab] OR "host response"[tiab])

E_medmed_markers
(MeMed[tiab] OR TRAIL[tiab] OR TNFSF10[tiab] OR "IP-10"[tiab] OR CXCL10[tiab] OR MX1[tiab]) AND (infection[tiab] OR sepsis[tiab] OR "host response"[tiab]) AND (diagnos*[tiab] OR biomarker*[tiab] OR "gene signature*"[tiab] OR "expression signature*"[tiab] OR assay*[tiab])

F_pmseq
(PMseq[tiab] OR "PM-seq"[tiab] OR "PMSEQ"[tiab])

G_cns_infect_tx
(meningit*[tiab] OR encephalit*[tiab] OR "central nervous system infection*"[tiab] OR "CNS infection*"[tiab]) AND (transcriptom*[tiab] OR "RNA-seq"[tiab] OR "RNA sequencing"[tiab] OR "gene expression"[tiab])

H_dualrnaseq
("dual RNA-seq"[tiab] OR "dual RNA sequencing"[tiab] OR "dual transcriptom*"[tiab])

I_hostdepletion
("host depletion"[tiab] OR "host read removal"[tiab] OR "rRNA depletion"[tiab] OR "ribosomal RNA depletion"[tiab]) AND (sequencing[tiab] OR metagenom*[tiab] OR transcriptom*[tiab])

J_sepsis_hostsig
(sepsis[tiab] OR septic[tiab]) AND ("host response"[tiab] OR "host transcriptom*"[tiab] OR "gene expression signature"[tiab] OR "transcriptomic signature"[tiab]) AND (diagnos*[tiab] OR biomarker*[tiab] OR classif*[tiab])

K_csf_mngs_clin
("cerebrospinal fluid"[tiab] OR CSF[tiab]) AND (mNGS[tiab] OR "metagenomic next-generation sequencing"[tiab] OR metatranscriptom*[tiab]) AND (infection[tiab] OR meningitis[tiab] OR encephalitis[tiab])

L_longread_mt
(nanopore[tiab] OR "long-read"[tiab] OR "Oxford Nanopore"[tiab]) AND (metatranscriptom*[tiab] OR "metagenomic sequencing"[tiab] OR mNGS[tiab])

M_tbm_host
(tuberculous meningitis[tiab] OR "TB meningitis"[tiab] OR "tuberculosis meningitis"[tiab]) AND (transcriptom*[tiab] OR "host response"[tiab] OR "gene expression"[tiab] OR RNA[tiab])

N_hostmrna_quant
("host mRNA"[tiab] OR "human mRNA"[tiab] OR "host transcript"[tiab]) AND (quantif*[tiab] OR abundanc*[tiab] OR "expression profile"[tiab] OR "read counts"[tiab])

O_hostresp_assay
("host response assay*"[tiab] OR "host response test*"[tiab] OR "host-response assay*"[tiab] OR "host response signature*"[tiab] OR "host transcriptomic assay*"[tiab])

P_septicyte_all
(SeptiCyte[tiab] OR SeptiScore[tiab] OR "MeMed BV"[tiab] OR FebriDx[tiab] OR "Immunexpress"[tiab] OR "host response panel*"[tiab])

Q_hostreads
("host reads"[tiab] OR "host sequences"[tiab] OR "human reads"[tiab] OR "non-pathogen reads"[tiab] OR "host-derived reads"[tiab] OR "host reads removal"[tiab])

R_hosttx_meta
("host transcriptom*"[tiab] OR "host gene expression"[tiab] OR "human transcriptom*"[tiab]) AND (metagenom*[tiab] OR metatranscriptom*[tiab] OR mNGS[tiab] OR "next-generation sequencing"[tiab])

S_clinicalmeta_host
("clinical metagenomics"[tiab] OR "clinical metagenomic"[tiab] OR "diagnostic metagenomic"[tiab] OR "metagenomic data"[tiab]) AND (host[tiab] OR human[tiab] OR transcriptom*[tiab] OR "RNA"[tiab])

T_csf_rnaseq_inf
("cerebrospinal fluid"[tiab] OR CSF[tiab] OR mening*[tiab] OR encephal*[tiab]) AND ("RNA sequencing"[tiab] OR "RNA-seq"[tiab] OR "transcriptomic profiling"[tiab] OR "transcriptome profiling"[tiab]) AND (infection[tiab] OR infectious[tiab] OR pathogen*[tiab] OR host[tiab] OR immune[tiab])

U_hostvsmicrobe
(host[tiab] AND (microb*[tiab] OR bacteri*[tiab] OR pathogen*[tiab])) AND (separat*[tiab] OR discriminat*[tiab] OR deplet*[tiab] OR classif*[tiab] OR benchmark*[tiab] OR differentiat*[tiab]) AND ("RNA-seq"[tiab] OR transcriptom*[tiab] OR metatranscriptom*[tiab] OR "gene expression"[tiab])

V_classifier_stability
(transcriptom*[tiab] OR "gene expression"[tiab] OR "expression signature*"[tiab]) AND (classifier*[tiab] OR "machine learning"[tiab] OR "diagnostic model"[tiab] OR signature*[tiab]) AND ("batch effect*"[tiab] OR preprocessing[tiab] OR "external validation"[tiab] OR reproducibility[tiab] OR "cross-platform"[tiab] OR "cross-cohort"[tiab] OR overfit*[tiab] OR "decision curve"[tiab] OR benchmark*[tiab]) AND (infection[tiab] OR sepsis[tiab] OR "host response"[tiab] OR "host transcriptom*"[tiab])

W_csf_hostmarker
(meningit*[tiab] OR encephalit*[tiab] OR "central nervous system infection*"[tiab] OR "CNS infection*"[tiab]) AND ("cerebrospinal fluid"[tiab] OR CSF[tiab]) AND ("host response"[tiab] OR proteom*[tiab] OR transcriptom*[tiab] OR "immune mediator*"[tiab] OR "host biomarker*"[tiab] OR "host gene"[tiab])

X_ml_hostresp_infection
("machine learning"[tiab] OR "deep learning"[tiab] OR transformer*[tiab] OR "neural network*"[tiab] OR classif*[tiab] OR "diagnostic model*"[tiab]) AND ("host response"[tiab] OR "host transcriptom*"[tiab] OR "host gene expression"[tiab] OR "gene expression signature*"[tiab] OR "transcriptomic signature*"[tiab] OR "host biomarker*"[tiab]) AND (infection[tiab] OR sepsis[tiab] OR meningit*[tiab] OR encephalit*[tiab] OR tuberculosis[tiab])

Y_ai_clinical_metagenomics
(transformer*[tiab] OR "foundation model*"[tiab] OR "large language model*"[tiab] OR "self-supervised"[tiab] OR "attention-based"[tiab]) AND (metagenom*[tiab] OR metatranscriptom*[tiab] OR mNGS[tiab] OR "host transcriptom*"[tiab] OR "gene expression signature*"[tiab]) AND (infection[tiab] OR pathogen*[tiab] OR sepsis[tiab] OR antimicrobial[tiab])

Z_lrti_host
(BALF[tiab] OR "bronchoalveolar lavage"[tiab] OR "lower respiratory tract infection*"[tiab] OR "tracheal aspirate*"[tiab] OR "lower airway"[tiab]) AND ("host response"[tiab] OR "host transcriptom*"[tiab] OR "host gene expression"[tiab] OR "transcriptomic signature*"[tiab] OR "gene expression signature*"[tiab] OR "RNA-seq"[tiab] OR "RNA sequencing"[tiab] OR metatranscriptom*[tiab]) AND (diagnos*[tiab] OR biomarker*[tiab] OR classif*[tiab] OR discriminat*[tiab] OR distinguish*[tiab])

AA_balf_mngs
(BALF[tiab] OR "bronchoalveolar lavage"[tiab] OR "lower respiratory"[tiab]) AND (mNGS[tiab] OR "metagenomic next-generation sequencing"[tiab] OR metatranscriptom*[tiab] OR "metagenomic sequencing"[tiab]) AND (host[tiab] OR "human reads"[tiab] OR "host response"[tiab] OR "host gene"[tiab] OR transcriptom*[tiab] OR "RNA-seq"[tiab])

AB_pathogen_class_host
(bacterial[tiab] AND (viral[tiab] OR fungal[tiab])) AND ("host response"[tiab] OR "host gene expression"[tiab] OR "host transcriptom*"[tiab] OR "gene expression signature*"[tiab] OR "transcriptomic signature*"[tiab] OR "host biomarker*"[tiab] OR "host RNA"[tiab]) AND (distinguish*[tiab] OR discriminat*[tiab] OR differentiat*[tiab] OR classif*[tiab])

AC_mngs_specimen_pathogen
(mNGS[tiab] OR "metagenomic next-generation sequencing"[tiab] OR "clinical metagenomic*"[tiab] OR "metagenomic sequencing"[tiab]) AND (BALF[tiab] OR "bronchoalveolar lavage"[tiab] OR "cerebrospinal fluid"[tiab] OR bloodstream[tiab] OR "blood sample*"[tiab] OR plasma[tiab]) AND (pathogen*[tiab] OR diagnos*[tiab])

AD_mngs_vs_conventional
(mNGS[tiab] OR "metagenomic next-generation sequencing"[tiab] OR "clinical metagenomic*"[tiab] OR tNGS[tiab] OR "targeted next-generation sequencing"[tiab]) AND (culture[tiab] OR PCR[tiab] OR "conventional microbiolog*"[tiab] OR "conventional method*"[tiab] OR "conventional test*"[tiab]) AND (compar*[tiab] OR concordance[tiab] OR "diagnostic performance"[tiab] OR sensitivity[tiab]) AND (infection*[tiab] OR infectious[tiab] OR pathogen*[tiab] OR pneumonia[tiab] OR sepsis[tiab] OR meningitis[tiab] OR encephalitis[tiab])

AE_mngs_microbiome_signal
(mNGS[tiab] OR metagenom*[tiab] OR metatranscriptom*[tiab]) AND (microbiome[tiab] OR microbiota[tiab] OR "microbial community"[tiab] OR coloniz*[tiab] OR colonis*[tiab]) AND (BALF[tiab] OR "bronchoalveolar lavage"[tiab] OR "lower respiratory"[tiab] OR "cerebrospinal fluid"[tiab] OR bloodstream[tiab] OR sepsis[tiab]) AND (infection*[tiab] OR diagnos*[tiab] OR pathogen*[tiab])

AF_fungal_dx
("invasive fungal"[tiab] OR "fungal infection*"[tiab] OR aspergill*[tiab] OR cryptococc*[tiab] OR pneumocystis[tiab] OR candidemia[tiab] OR candidaemia[tiab]) AND (mNGS[tiab] OR "metagenomic next-generation sequencing"[tiab] OR "host response"[tiab] OR "host transcriptom*"[tiab] OR "gene expression signature*"[tiab] OR "host biomarker*"[tiab]) AND (diagnos*[tiab] OR discriminat*[tiab] OR distinguish*[tiab])

AG_immune_signature_infection
("immune signature*"[tiab] OR "immune response signature*"[tiab] OR "immune profil*"[tiab] OR "immune transcriptom*"[tiab]) AND (transcriptom*[tiab] OR "RNA-seq"[tiab] OR "RNA sequencing"[tiab] OR "gene expression"[tiab]) AND (infection*[tiab] OR sepsis[tiab]) AND (classif*[tiab] OR diagnos*[tiab] OR distinguish*[tiab] OR discriminat*[tiab])

```
