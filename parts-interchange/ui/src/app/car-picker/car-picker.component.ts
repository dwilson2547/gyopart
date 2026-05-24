import { Component, OnChanges, OnInit, SimpleChanges } from '@angular/core';
import { MessageService, Message, MessageQueues } from 'src/services/message.service';
import { TreeService } from 'src/services/tree.service';

@Component({
  selector: 'app-car-picker',
  templateUrl: './car-picker.component.html',
  styleUrls: ['./car-picker.component.scss'],
  providers: [TreeService]
})
export class CarPickerComponent implements OnInit {
  years: any = [];
  makes: any = [];
  models: any = [];
  trims: any = [];
  engines: any = [];
  car: any = [];

  ddlYear: any;
  ddlMake: any;
  ddlModel: any;
  ddlTrim: any;
  ddlEngine: any;

  year_id: number = 0;
  make_id: number = 0;
  model_id: number = 0;
  trim_id: number = 0;
  engine_id: number = 0;

  constructor(private treeService: TreeService, private messageService: MessageService) { }

  ngOnInit(): void {
    this.load();
  }

  load() {
    this.treeService.get_years().subscribe((data) => {
      this.years = data;
      console.log('called')
    })
  }

  set_year() {
    this.treeService.get_makes(this.ddlYear).subscribe((data) => {
      this.makes = data;
      this.ddlMake = [];
      this.ddlModel = [];
      this.ddlTrim = [];
      this.ddlEngine = [];
      this.engines = [];
      this.trims = [];
      this.models = [];
    })
  }
  set_make() {
    this.treeService.get_models(this.ddlYear, this.ddlMake).subscribe((data) => {
      this.models = data;
      this.ddlModel = [];
      this.ddlTrim = [];
      this.ddlEngine = [];
      this.engines = [];
      this.trims = [];
    })
  }
  set_model() {
    this.treeService.get_trims(this.ddlYear, this.ddlMake, this.ddlModel).subscribe((data) => {
      this.trims = data;
      this.ddlTrim = [];
      this.ddlEngine = [];
      this.engines = [];
    })
  }
  set_trim() {
    this.treeService.get_engines(this.ddlYear, this.ddlMake, this.ddlModel, this.ddlTrim).subscribe((data) => {
      this.engines = data;
      this.ddlEngine = [];
    })
  }
  set_engine() {
    this.treeService.get_cars(this.ddlYear, this.ddlMake, this.ddlModel, this.ddlTrim, this.ddlEngine).subscribe((data: any) => {
      this.car = data[0];
      let msg = new Message(MessageQueues.CAR_PICKER_QUEUE, this.car);
      this.messageService.sendMessage(msg);
    })
  }

}
