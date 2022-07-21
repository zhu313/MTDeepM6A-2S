# MTDeepM6A-2S: a two-stage multi-task deep learning model for predicting RNA N6-methyladenosine sites of Saccharomyces cerevisiae
# This is the stage I model

1. All data of stage I we used is in ./data/.

2. To predict low resolution m6A from a fasta file, please follow these steps:
   Predict m6A sites using your fasta file. Please use tensorflow==1.31.1 and keras==2.2.4 to run:
     cd ./codes/predict
     python2 ./predict_RAC.py ./example.fasta modelpath result.txt

3. To retrain the model, please use the following commands:
     cd ./codes/retrain
     python2 ./train_xxx.py
