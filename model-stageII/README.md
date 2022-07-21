# MTDeepM6A-2S: a two-stage multi-task deep learning model for predicting RNA N6-methyladenosine sites of Saccharomyces cerevisiae
# This is the stage II model

1. All data of stage II we used is in ./data/.

2. To predict base resolution m6A sites from a fasta file, please follow these steps:
   Predict m6A sites using your fasta file. Please use tensorflow==1.31.1 and keras==2.2.4 to run:
     cd ./codes/predict
     python2 ./GAC_tf_predict.py ./example.fasta modelpath result.txt
Note: you can also predict the base resolution m6A sites from the low resolution m6A sites predicted by stage I model.

3. To retrain the model, please use the following commands:
     cd ./codes/retrain
     python2 ./GAC_tf_retrain.py
